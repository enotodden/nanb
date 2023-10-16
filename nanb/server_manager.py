import os
import sys
import time
import uuid
import subprocess
import signal

from nanb.config import C


class ServerManager:
    """
    ServerManager holds the server process
    """

    def __init__(self):
        self.socket_file = None
        self.server_log_file = open(C.server_log_file, "w")

    def start(self):
        """
        Generate a random socket file name and start the server.
        Returns once the server has generated the socket file.
        """
        socket_uuid = uuid.uuid4().hex
        self.socket_file = C.socket_prefix + socket_uuid

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        self.server = subprocess.Popen(
            [sys.executable, "-m", "nanb.server", "--socket-file", self.socket_file],
            stdout=self.server_log_file,
            stderr=self.server_log_file,
            env=env,
        )

        # Wait until the server comes up and starts listening
        # FIXME: Timeout
        while True:
            if os.path.exists(self.socket_file):
                break
            time.sleep(0.1)

    def stop(self):
        """
        Stop the server.
        Try nicely at first, but if shutdown takes too long, we kill it and
        remove the socket file ourselves.
        """
        self.server.terminate()
        try:
            self.server.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self.server.kill()
            self.server.wait()
        if os.path.exists(self.socket_file):
            os.remove(self.socket_file)

    def restart(self):
        """
        Restart the server
        """
        self.stop()
        self.start()

    def interrupt(self):
        """
        Send SIGUSR1 which is hooked up to generate a KeyboardInterrupt in
        the server.
        """
        self.server.send_signal(signal.SIGUSR1)
