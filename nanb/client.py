import socket
import asyncio
import argparse


class UnixDomainClient:
    def __init__(self, filename):
        self.filename = filename
        self.socket = None

    async def run_code(self, line_start: int, source: str, q: asyncio.Queue):
        reader, writer = await asyncio.open_unix_connection(self.filename)

        header = f"{len(source)}%{line_start}\n"
        writer.write(header.encode())
        writer.write(source.encode())
        await writer.drain()

        exc = None
        try:
            while True:
                output = await reader.read(1024)
                if not output:
                    break
                await q.put(output.decode())
        except asyncio.CancelledError:
            print("Cancelled")
        except Exception as e:
            print(f"Exception: {e}")
            exc = e
        finally:
            writer.close()
            await writer.wait_closed()

        if exc:
            raise exc


if __name__ == "__main__":
    argp = argparse.ArgumentParser()
    argp.add_argument("-s", "--socket-file", default="/tmp/nanb_socket")
    args = argp.parse_args()
    filename = args.socket_file
    client = UnixDomainClient(filename)
    q = asyncio.Queue()
    asyncio.run(client.run_code(0, "print('Hello, world!')", q))
    while not q.empty():
        print(q.get_nowait())
