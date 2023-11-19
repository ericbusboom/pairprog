import json
import subprocess
import time
from pathlib import Path
import atexit

import zmq
from jupyter_client import BlockingKernelClient


class IpyKernel:
    def __init__(self, connection_path=None):
        self.kernel_process = None


        if connection_path is None:
            self.connection_path = Path.cwd().joinpath(".ipyconnection.json")
        else:
            self.connection_path = Path(connection_path)

        self.connection_path = self.connection_path.resolve()

        self.connection = None  # Connection info for the IPython kernel

        self.client = None  # Kernel client

        self.messages = {}  # Messages received from the kernel

    def start(self):
        # Start the IPython kernel as a subprocess
        import sys
        ipy_exec = Path(__file__).parent / "cli" / "ipy.py"


        print("Starting kernel process connecting to", self.connection_path)


        self.kernel_process = subprocess.Popen(
            [
                sys.executable,
                str(ipy_exec),
                "kernel",
                f"--IPKernelApp.connection_file={self.connection_path}",
            ],
            stdout=subprocess.PIPE,
        )

        print("Looking for connection file", self.connection_path)
        while not self.connection_path.exists():
            time.sleep(0.1)

        print ("connection file exists")

        self.client = BlockingKernelClient(connection_file=str(self.connection_path))

        self.client.load_connection_file()
        self.client.start_channels()

    def exec(self, code):
        from queue import Empty

        msgid = self.client.execute(code)

        self.messages[msgid] = []
        while True:

            try:
                reply = self.client.get_iopub_msg(timeout=5)
                parent = reply["parent_header"]
                if parent.get("msg_id") == msgid:
                    del reply["parent_header"]

                    self.messages[msgid].append(reply)
                    print(reply['msg_type'], reply["content"])
                    if reply["content"].get("execution_state") == "idle":
                        break
            except Empty:
                print("timeout")
                break

    def stop(self):
        # Clean up: close the socket and terminate the kernel

        if self.kernel_process is not None:
            self.kernel_process.terminate()

    # stop when the object is deleted
    def __del__(self):
        self.stop()





def main():
    # Start the IPython kernel
    from time import sleep

    ipy = IpyKernel()
    ipy.start()
    atexit.register(ipy.stop)
    sleep(3)
    ipy.exec('print("hello world")')
    ipy.stop()


if __name__ == "__main__":
    main()
