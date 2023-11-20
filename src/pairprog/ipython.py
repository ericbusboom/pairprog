import atexit
import logging
from collections import defaultdict
from textwrap import dedent

from jupyter_client import KernelManager

logger = logging.getLogger(__name__)


class KernelException(Exception):
    """Exception from the IPython kernel"""


class IpyKernel:
    startup_code = dedent(f"""
    %load_ext autoreload
    %autoreload 2
    """).strip()

    def __init__(self):

        self.client = None  # Kernel client

        self.kernel_process = None  # When the kernel is started as a subprocess
        self.kernel_manager = None  # When the kerneed is managed by KernelManager

        self.messages = defaultdict(list)  # Messages received from the kernel

    def start(self):
        """Start the kernel and the client"""

        from os import environ

        # To supress frozen modules warning

        environ['PYDEVD_DISABLE_FILE_VALIDATION'] = '1'

        #import warnings;
        #warnings.simplefilter('ignore')

        self.kernel_manager = KernelManager()
        self.kernel_manager.start_kernel()
        self.client = self.kernel_manager.blocking_client()
        self.client.start_channels()
        self.exec(self.startup_code, timeout=None)

    def stop(self):
        # Clean up: close the socket and terminate the kernel

        if self.client is not None:
            self.client.shutdown()
            self.client = None

        if self.kernel_process is not None:
            self.kernel_process.terminate()
            self.kernel_process = None

        if self.kernel_manager is not None:
            self.kernel_manager.shutdown_kernel()
            self.kernel_manager = None

    def get_var(self, varname):
        """Return a named variable from the kernel in json format.
        Pandas dataframes and most variables will be returned as json, if possible
                strings will be returned as strings, and on error, just use repr()"""

        code = f"""
        from pairprog import serialize
        print(serialize({varname}))
        """

        e = self.exec(code)
        try:
            return e[1].strip()
        except Exception as e:
            logger.debug((str(e)))
            logger.debug("Response: " + str(e))
            raise

    # noinspection PyShadowingNames
    def return_stream(self, msgid: str):
        for m in reversed(self.messages[msgid]):
            if m['msg_type'] == 'stream':
                return m
        else:
            return None  # not all code returns output, such ass assignments

    def exec(self, code: str, timeout: int | None = 5):
        """Execute code on the kernel"""

        from queue import Empty

        msgid = self.client.execute(code)
        logger.debug(f"Execute code, ({code[:20]}...),  msgid={msgid}")

        if timeout is None:
            return None, None

        while True:

            try:
                reply = self.client.get_iopub_msg(timeout=5)
                parent = reply["parent_header"]

                self.messages[parent.get("msg_id")].append(reply)

                if parent.get("msg_id") == msgid:
                    del reply["parent_header"]

                    logger.debug(f"{msgid}: {reply['msg_type']} {reply['content']} {reply}")

                    if reply["content"].get("execution_state") == "idle":
                        sm = self.return_stream(msgid)
                        if sm is not None:
                            return msgid, sm["content"]['text']
                        else:
                            return msgid, None

                    if reply["msg_type"] == "error":
                        raise KernelException('\n\n' + ('\n-----\n'.join(reply['content']['traceback'])))

            except Empty:
                print("timeout")
                return None, None

    # stop when the object is deleted
    def __del__(self):
        self.stop()


def main():
    # Start the IPython kernel
    from time import sleep
    logging.basicConfig(level=logging.INFO)
    logger.setLevel(logging.DEBUG)

    ipy = IpyKernel()
    ipy.start()
    atexit.register(ipy.stop)

    sleep(3)
    mid, o = ipy.exec('word = "hello world"\nprint(word)')
    print(mid, o)
    mid, o = ipy.exec('%who')
    print(mid, o)
    o = ipy.get_var('word')
    print(o)

    mid, o = ipy.exec('a = [1,2,3,4,5]')
    o = ipy.get_var('a')
    print(o)

    ipy.stop()


if __name__ == "__main__":
    main()
