import json
import subprocess
import time

import zmq

# Start the IPython kernel as a subprocess
kernel_process = subprocess.Popen(
    ["ipython", "kernel", "--IPKernelApp.connection_file=my_connection_file.json"],
    stdout=subprocess.PIPE,
)

# Wait a bit for the kernel to start and write the connection file
time.sleep(5)

# Read the connection file written by the IPython kernel
with open("my_connection_file.json", "r") as f:
    connection_info = json.load(f)

# Setup the ZeroMQ context and socket
context = zmq.Context()
client = context.socket(zmq.REQ)

# Connect to the IPython kernel
connection_string = f"tcp://{connection_info['ip']}:{connection_info['shell_port']}"
client.connect(connection_string)


# Function to send a command to the kernel
def send_command(command):
    # IPython kernel communication uses JSON with 'content' field for code
    msg = json.dumps({"content": {"code": command}})
    client.send_string(msg)

    # Receive the reply from the kernel
    reply = client.recv()
    print("Reply:", reply)


if False:
    # Example command
    send_command("print('Hello from IPython kernel')")

    # Clean up: close the socket and terminate the kernel
    client.close()
    context.term()
    kernel_process.terminate()
