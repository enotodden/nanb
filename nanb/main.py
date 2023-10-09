import os
import sys
import time
import argparse
import signal
import asyncio
import subprocess
import hashlib
import uuid

import textual
import textual.app
import rich
import rich.markdown
import rich.spinner
from textual.reactive import reactive

from watchfiles import awatch

from nanb.cell import Cell, MarkdownCell, CodeCell, match_cells
from nanb.config import Config, read_config
from nanb.client import UnixDomainClient

from nanb.widgets import MarkdownSegment, CodeSegment, Output, FooterWithSpinner

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

def split_to_cells(source) -> [Cell]:

    source = source.rstrip()

    out = []
    lines = []
    start_line = 0
    celltype = "code"
    cellname = None
    for i, line in enumerate(source.split("\n")):
        if line.startswith("# ---") or line.startswith("# ==="):
            if lines:
                out.append((celltype, cellname, start_line, i-1, "\n".join(lines)))
            cellname = line[5:].strip()
            if cellname == "":
                cellname = None
            else:
                cellname = cellname
            if line.startswith("# ---"):
                celltype = "code"
            else:
                celltype = "markdown"
            start_line = i+1
            lines = []
        else:
            if celltype == "markdown":
                if line != "" and not line.startswith("#"):
                    raise Exception(f"Markdown cell at line {i} contains non-empty line that doesn't start with #")
            lines.append(line)
    if lines:
        out.append((celltype, cellname, start_line, i-1, "\n".join(lines)))

    cells = []

    for celltype, cellname, line_start, line_end, src in out:
        if celltype == "markdown":
            cells.append(MarkdownCell(cellname, src, line_start, line_end))
        elif celltype == "code":
            cells.append(CodeCell(cellname, src, line_start, line_end))
        else:
            raise Exception(f"Unknown cell type {celltype}")

    return cells

def load_file(filename: str) -> [Cell]:
    with open(filename, "r") as f:
        return split_to_cells(f.read())


class Cells(textual.containers.VerticalScroll):

    cells = textual.reactive.var([])

    def __init__(self, cells, **kwargs):
        self.cells = cells
        super().__init__(**kwargs)

    def make_widgets(self):
        widgets = []
        for i, cell in enumerate(self.cells):
            classes = "segment"
            if i == len(self.cells)-1:
                classes += " last"
            if cell.cell_type == "markdown":
                w = MarkdownSegment(i, cell, classes=classes, id=f"segment_{i}")
            elif cell.cell_type == "code":
                w = CodeSegment(i, cell, classes=classes, id=f"segment_{i}")
            w.on_clicked = self.on_segment_clicked
            widgets.append(w)
        return widgets

    def focus_cell(self, cell: Cell):
        for i, w in enumerate(self.widgets):
            if w.cell == cell:
                self.currently_focused = i
                w.focus()
                self.on_output(w.cell)
                break

    def focus_widget(self, w):
        self.focus_cell(w.cell)

    def focus_idx(self, idx):
        self.focus_cell(self.cells[idx])

    def compose(self) -> textual.app.ComposeResult:
        widgets = self.make_widgets()
        self.widgets = widgets
        for w in widgets:
            yield w

    def on_segment_clicked(self, w):
        self.focus_widget(w)

    def on_mount(self):
        self.focus_idx(0)

    async def on_key(self, event: textual.events.Key) -> None:
        if event.key == "up":
            if self.currently_focused > 0:
                self.focus_idx(self.currently_focused - 1)
        elif event.key == "down":
            if self.currently_focused < len(self.widgets) - 1:
                self.focus_idx(self.currently_focused + 1)
        if event.key == "enter":
            self.on_run_code(self.widgets[self.currently_focused])

    @property
    def current(self):
        if self.currently_focused is None:
            return None
        return self.widgets[self.currently_focused]

    def clear(self):
        q = self.query(".segment")
        await_remove = q.remove()
        self.currently_focused = None
        return await_remove

    async def refresh_cells(self, cells):
        self.cells = cells
        self.widgets = self.make_widgets()
        await self.clear()
        self.mount(*self.widgets)
        self.focus_idx(0)

CSS = open(os.path.join(THIS_DIR, "nanb.css")).read()

class ServerManager:

    def __init__(self, server_log_file="nanb_server.log"):
        self.socket_file = None
        self.server_log_file = open(server_log_file, "w")

    def start(self):
        socket_uuid = uuid.uuid4().hex
        self.socket_file = "/tmp/nanb_socket_" + socket_uuid

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        self.server = subprocess.Popen([
                sys.executable,
                "-m",
                "nanb.server",
                "--socket-file",
                self.socket_file
            ],
            stdout=self.server_log_file,
            stderr=self.server_log_file,
            env=env
        )

        # Wait until the server comes up and starts listening
        while True:
            if os.path.exists(self.socket_file):
                break
            time.sleep(0.1)

    def stop(self):
        self.server.terminate()
        self.server.wait()

    def restart(self):
        self.stop()
        self.start()

from textual.binding import Binding

class App(textual.app.App):

    BINDINGS = [
        Binding(key="q", action="quit", description="Quit"),
        Binding(key="ctrl+r", action="restart_kernel", description="Restart Kernel"),
    ]

    def __init__(self, config: Config, cells, server_log_file, filename, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_running_code = False
        self.output = None
        self.CSS = CSS
        if config.css:
            self.CSS += "\n" + config.css
        self.cells = cells
        self.filename = filename
        self.task_queue = asyncio.Queue()
        self.sm = ServerManager(server_log_file)
        self.sm.start()
        self.client = UnixDomainClient(self.sm.socket_file)

    def exit(self, *args, **kwargs):
        self.sm.stop()
        super().exit(*args, **kwargs)

    def action_restart_kernel(self):
        self.footer.resume_spinner()
        self.clear_task_queue()
        self.sm.restart()
        self.client = UnixDomainClient(self.sm.socket_file)
        self.footer.pause_spinner()

    def on_output(self, cell: Cell):
        self.output.use_cell(cell)

    def on_mount(self):
        self.footer.pause_spinner()

    def compose(self) -> textual.app.ComposeResult:
        with textual.containers.Container(id="app-grid"):
            self.cellsw = Cells(self.cells, id="cells")
            self.cellsw.on_output = self.on_output
            self.cellsw.on_run_code = self.run_code
            yield self.cellsw
            with textual.containers.Container(id="output"):
                self.output = Output()
                yield self.output
        self.footer = FooterWithSpinner()
        yield self.footer

        loop = asyncio.get_event_loop()
        self.process_task_queue_task = asyncio.create_task(self.process_task_queue())
        self.watch_sourcefile_task = asyncio.create_task(self.watch_sourcefile())

    async def process_task_queue(self):
        while True:
            w = await self.task_queue.get()
            loop = asyncio.get_event_loop()
            w.cell.output = ""
            w.state = "RUNNING"

            q = asyncio.Queue()
            task = loop.create_task(self.client.run_code(w.cell.line_start, w.cell.source, q))

            started = False

            self.footer.resume_spinner()
            while not task.done():
                try:
                    result = await asyncio.wait_for(q.get(), timeout=0.2)
                    if not result:
                        continue
                    if not started:
                        started = True
                        w.cell.output = ""
                        w.state = "RUNNING"
                    w.cell.output += result

                    self.output.use_cell(self.cellsw.current.cell)
                except asyncio.TimeoutError:
                    pass
            self.footer.pause_spinner()
            w.state = ""

    async def watch_sourcefile(self):
        async for changes in awatch(self.filename):
            for change, _ in changes:
                if change == 2:
                    await self.reload_source()

    async def reload_source(self):
        with open(self.filename) as f:
            try:
                source = f.read()
                new_cells = split_to_cells(source)
                match_cells(self.cells, new_cells)
                self.cells = new_cells
                await self.cellsw.refresh_cells(self.cells)
                self.output.use_cell(self.cellsw.current.cell)
                self.clear_task_queue()
            except Exception as exc:
                print(exc)
                self.exit(1)

    @textual.work()
    async def run_code(self, w):
        if w.cell.cell_type != "code":
            return
        w.state = "PENDING"
        await self.task_queue.put(w)

    def clear_task_queue(self):
        while not self.task_queue.empty():
            try:
                self.task_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        for w in self.cellsw.widgets:
            w.state = ""


def main():
    argp = argparse.ArgumentParser()
    argp.add_argument("-c", "--config-dir", default=os.path.join(os.path.expanduser("~"), ".nanb"))
    argp.add_argument("-L", "--server-log-file", default="nanb_server.log")

    subp = argp.add_subparsers(dest='command', required=True)

    subp_run = subp.add_parser("run")
    subp_run.add_argument("file")

    args = argp.parse_args()

    if not os.path.exists(args.config_dir):
        sys.stderr.write(f"ERROR: Config directory '{args.config_dir}' does not exist\n")
        sys.exit(1)
        return

    config = read_config(args.config_dir)

    if args.command == "run":
        with open(args.file) as f:
            source = f.read()
            cells = split_to_cells(source)
            App(config, cells, args.server_log_file, args.file).run()
    else:
        sys.stderr.write(f"ERROR: Unknown command '{args.command}'\n")

if __name__ == "__main__":
    main()
