import signal
import _thread
import socketserver
import os
import io
import code
import ast
import contextlib
import argparse
from dataclasses import dataclass

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

PRINT_LAST_EXPR = """
_ = {}
if _ is not None:
    print(_)
"""

class IO(io.IOBase):

    def __init__(self, on_output):
        super().__init__()
        self.streampos = 0
        self.on_output = on_output

    def close(self):
        pass

    def closed(self) -> bool:
        return False

    def fileno(self) -> int:
        return None

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False

    def readable(self) -> bool:
        return False

    def readline(self, *args):
        return None

    def readlines(self, *args):
        return None

    def seek(self, *args):
        pass

    def seekable(self) -> bool:
        return False

    def tell(self) -> int:
        return self.streampos

    def truncate(self, *args):
        pass

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        self.streampos += len(s)
        self.on_output(s)
        return len(s)

    def writelines(self, lines, *args):
        for line in lines:
            self.write(line)

@dataclass
class Header:
    source_bytes: int
    line_start: int

def parse_header(header_data: str):
    source_bytes, line_start = header_data.split("%")
    return Header(int(source_bytes), int(line_start))

class Runtime:

    def __init__(self):
        self.interpreter = code.InteractiveInterpreter()

    def run_code(self, line_start:int, source: str, outfile: IO):
        with contextlib.redirect_stdout(outfile):
            with contextlib.redirect_stderr(outfile):
                # If the last statement is an expression, we print the result
                # of it, like jupyter would
                last = None
                stmts = list(ast.iter_child_nodes(ast.parse(source)))
                if isinstance(stmts[-1], ast.Expr):
                    # We get rid of the last statement from the source
                    # because it can be a function call, and we don't want
                    # to call it twice
                    source = ast.unparse(stmts[:-1])
                    last = PRINT_LAST_EXPR.format(ast.unparse(stmts[-1].value))

                # Run the script, except for the last expression if the last statement
                # is an expression
                self.interpreter.runsource(source, symbol='exec')

                # If the last statement was an expression, it will be assigned to _
                # and we print it
                if last is not None:
                    self.interpreter.runsource(last, symbol='exec')


RUNTIME = Runtime()


class ServerHandler(socketserver.StreamRequestHandler):
    def __init__(self, *args, **kwargs):
        self.runtime = RUNTIME
        super().__init__(*args, **kwargs)

    def on_output(self, output):
        self.wfile.write(output.encode())
        self.wfile.flush()

    def run_code(self, line_start, source):
        outfile = IO(self.on_output)
        self.runtime.run_code(line_start, source, outfile)

    def handle(self):
        print("Connection opened")
        try:
            header_data = self.rfile.readline().decode().strip()
            if not header_data:
                return
            header = parse_header(header_data)
            data = self.rfile.read(header.source_bytes).decode()
            self.run_code(header.line_start, data)
        except BrokenPipeError:
            print("Broken pipe")
        finally:
            print("Connection closed")
            self.wfile.close()

class UnixDomainServer:

    def __init__(self, filename):
        self.filename = filename
        if os.path.exists(filename):
            os.remove(filename)
        self.server = socketserver.UnixStreamServer(filename, ServerHandler)

    def run(self):
        try:
            # Start the server
            print(f"Server listening on {self.filename}")
            self.server.serve_forever(0.1)
        except KeyboardInterrupt:
            # Handle keyboard interrupt
            print("Server stopped")
        finally:
            # Clean up by removing the socket file
            self.server.server_close()
            os.remove(self.filename)

    def shutdown(self):
        self.server.shutdown()


def main():
    argp = argparse.ArgumentParser()
    argp.add_argument("-m", "--mode", choices=["unix-domain"], default="unix-domain")
    argp.add_argument("-s", "--socket-file", default="/tmp/nanb_socket")
    args = argp.parse_args()
    filename = args.socket_file

    server = UnixDomainServer(filename)

    def stop_server():
        server.shutdown()
        if os.path.exists(args.socket_file):
            os.remove(args.socket_file)
        os.exit(0)

    def sighandler(s, m_):
        _thread.start_new_thread(stop_server, ())
    signal.signal(signal.SIGTERM, sighandler)

    server.run()

if __name__ == "__main__":
    main()
