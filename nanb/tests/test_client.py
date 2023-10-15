import unittest
import uuid
import sys
import os
import subprocess
import asyncio
import time
import signal

from nanb.client import UnixDomainClient

class TestClient(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.socket_file = f"/tmp/nanb-test-{uuid.uuid4().hex}.sock"
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        server_log_file = sys.stdout
        print("SOCKET FILE", self.socket_file)
        self.server = subprocess.Popen([
                sys.executable,
                "-m",
                "nanb.server",
                "--socket-file",
                self.socket_file
            ],
            stdout=sys.stdout,
            stderr=sys.stderr,
            env=env
        )
        while True:
            if os.path.exists(self.socket_file):
                break
            time.sleep(0.1)
        self.loop = asyncio.get_event_loop()

    def tearDown(self):
        self.server.terminate()
        self.server.wait()

    async def test_basic(self):
        cl1 = UnixDomainClient(self.socket_file)
        q1 = asyncio.Queue()
        t = self.loop.create_task(cl1.run_code(0, """print("foo")""", q1))
        out = await q1.get()
        self.assertEqual(out, "foo\n")

    async def test_ordering(self):
        """"
        Starts one client, sleeps, then outputs.
        Starts a second one to ensure that doesn't start
        until the first one is done.
        """
        cl1 = UnixDomainClient(self.socket_file)
        q1 = asyncio.Queue()
        t = self.loop.create_task(cl1.run_code(0, """import time; time.sleep(1); print("foo")""", q1))
        await asyncio.sleep(0.2)
        cl2 = UnixDomainClient(self.socket_file)
        q2 = asyncio.Queue()
        t = self.loop.create_task(cl2.run_code(0, """print("bar")""", q2))
        out = await q2.get()
        self.assertEqual(out, "bar\n")
        out = await q1.get()
        self.assertEqual(out, "foo\n")

    async def test_interrupt(self):
        cl1 = UnixDomainClient(self.socket_file)
        q1 = asyncio.Queue()
        t = self.loop.create_task(cl1.run_code(0, """foo='bar'""", q1))
        await asyncio.sleep(1)
        t = self.loop.create_task(cl1.run_code(0, """import time; time.sleep(1000)""", q1))
        await asyncio.sleep(1)
        self.server.send_signal(signal.SIGUSR1)

        t = self.loop.create_task(cl1.run_code(0, """print(foo)""", q1))
        out = await q1.get()
        self.assertTrue("KeyboardInterrupt" in out)

        out = await q1.get()
        self.assertEqual(out, "bar\n")
