import json
import subprocess
import time
from pathlib import Path

import zmq
from jupyter_client import BlockingKernelClient


class IpyKernel:
    def __init__(self, connection_path="./.ipy_connection.json"):
        self.kernel_process = None

        self.connection_path = Path(connection_path)

        self.connection = None  # Connection info for the IPython kernel

        self.client = None  # Kernel client

    def start(self):
        # Start the IPython kernel as a subprocess
        self.kernel_process = subprocess.Popen(
            [
                "ipython",
                "kernel",
                f"--IPKernelApp.connection_file={self.connection_path}",
            ],
            stdout=subprocess.PIPE,
        )

        while not self.connection_path.exists():
            time.sleep(0.1)

        self.client = BlockingKernelClient(connection_file=self.connection_path)

        self.client.load_connection_file()
        self.client.start_channels()

    def exec(self, code):
        while True:
            msgid = self.client.execute(code)
            reply = self.client.get_shell_msg(timeout=5)
            print(reply["content"])
            if reply["content"]["execution_state"] == "idle":
                break

    def start2(self):
        # Read the connection file written by the IPython kernel
        with open(self.connection_path, "r") as f:
            self.connection = json.load(f)

        # Setup the ZeroMQ context and socket
        self.context = zmq.Context()
        self.client = self.context.socket(zmq.REQ)

        # Connect to the IPython kernel
        connection_string = (
            f"tcp://{self.connection['ip']}:{self.connection['shell_port']}"
        )
        self.client.connect(connection_string)

    def stop(self):
        # Clean up: close the socket and terminate the kernel
        self.client.close()
        self.context.term()
        self.kernel_process.terminate()

    # stop when the object is deleted
    def __del__(self):
        self.stop()

    # Function to send a command to the kernel
    def send_command(self, command):
        # IPython kernel communication uses JSON with 'content' field for code
        msg = json.dumps({"content": {"code": command}})
        self.client.send_string(msg)

        # Receive the reply from the kernel
        reply = self.client.recv()
        print("Reply:", reply)


# main and text fuction


def main():
    # Start the IPython kernel
    ipy = IpyKernel()
    ipy.start()
    ipy.exec('print("hello world")')
    ipy.stop()


if __name__ == "__main__":
    main()
