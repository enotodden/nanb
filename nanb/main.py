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
from textual.binding import Binding

from watchfiles import awatch

from nanb.cell import Cell, MarkdownCell, CodeCell, match_cells
from nanb.config import Config, read_config, load_config, C
from nanb.client import UnixDomainClient
from nanb.server_manager import ServerManager
from nanb.help_screen import HelpScreen

from nanb.widgets import (
    MarkdownSegment,
    CodeSegment,
    Output,
    FooterWithSpinner,
    CellList,
)

THIS_DIR = os.path.dirname(os.path.abspath(__file__))


def split_to_cells(source) -> [Cell]:

    source = source.rstrip()

    out = []
    lines = []
    start_line = 0
    celltype = "code"
    cellname = None
    for i, line in enumerate(source.split("\n")):
        if line.startswith("# ---") or line.strip() == r"# %%%":
            if lines:
                if celltype == "markdown":
                    lines = [l[1:] for l in lines]
                out.append((celltype, cellname, start_line, i - 1, "\n".join(lines)))
            cellname = line[5:].strip()
            if cellname == "":
                cellname = None
            else:
                cellname = cellname
            if line.startswith("# ---"):
                celltype = "code"
            else:
                celltype = "markdown"
            start_line = i + 2  # skip the --- line
            lines = []
        else:
            if celltype == "markdown":
                if line != "" and not line.startswith("#"):
                    raise Exception(
                        f"Markdown cell at line {i} contains non-empty line that doesn't start with #"
                    )
            lines.append(line)
    if lines:
        if celltype == "markdown":
            lines = [l[1:] for l in lines]
        out.append((celltype, cellname, start_line, i - 1, "\n".join(lines)))

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


CSS = open(os.path.join(THIS_DIR, "nanb.css")).read()


class AppLogic:
    def __init__(self, cells, server_log_file, filename, *args, **kwargs):
        self.is_running_code = False
        self.output = None
        self.CSS = CSS
        if C.css is not None:
            self.CSS += "\n" + C.css
        self.cells = cells
        self.filename = filename
        self.task_queue = asyncio.Queue()
        self.sm = ServerManager()
        self.sm.start()
        self.client = UnixDomainClient(self.sm.socket_file)

    def exit(self, *args, **kwargs):
        self.sm.stop()
        super().exit(*args, **kwargs)

    def action_help(self):
        self.push_screen(HelpScreen())

    def action_restart_kernel(self):
        self.footer.resume_spinner()
        self.clear_task_queue()
        self.sm.restart()
        self.client = UnixDomainClient(self.sm.socket_file)
        self.footer.pause_spinner()

    def action_interrupt(self):
        self.footer.resume_spinner()
        self.clear_task_queue()
        self.sm.interrupt()
        self.footer.pause_spinner()

    def action_clear_cell_output(self):
        if self.cellsw.current_cell is not None:
            self.cellsw.current_cell.output = ""
            self.on_output(self.cellsw.current_cell)

    def action_clear_all(self):
        for cell in self.cells:
            cell.output = ""
        if self.cellsw.current_cell is not None:
            self.on_output(self.cellsw.current_cell)

    def action_run_all(self):
        for cell in self.cells:
            self.run_code(cell)

    def action_run_cell(self):
        self.run_code(self.cellsw.current_cell)

    def on_output(self, cell: Cell):
        self.output.use_cell(cell)

    def on_mount(self):
        self.footer.pause_spinner()

    def _compose(self):
        with textual.containers.Container(id="app-grid"):
            self.cellsw = CellList(self.cells, id="cells")
            self.cellsw.on_output = self.on_output
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
            cell = await self.task_queue.get()
            loop = asyncio.get_event_loop()
            cell.output = ""
            self.cellsw.set_cell_state(cell, C.tr["state_running"])

            q = asyncio.Queue()
            task = loop.create_task(
                self.client.run_code(cell.line_start, cell.source, q)
            )

            started = False

            self.footer.resume_spinner()
            while not task.done():
                try:
                    result = await asyncio.wait_for(q.get(), timeout=0.2)
                    if not result:
                        continue
                    if not started:
                        started = True
                        cell.output = ""
                        self.cellsw.set_cell_state(cell, C.tr["state_running"])
                    cell.output += result

                    self.output.use_cell(self.cellsw.current_cell)
                except asyncio.TimeoutError:
                    pass
            self.footer.pause_spinner()
            self.cellsw.set_cell_state(cell, "")

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
                self.output.use_cell(self.cellsw.current_cell)
                self.clear_task_queue()
            except Exception as exc:
                print(exc)
                self.exit(1)

    @textual.work()
    async def run_code(self, cell: Cell):
        if cell.cell_type != "code":
            return
        self.cellsw.set_cell_state(cell, C.tr["state_pending"])
        await self.task_queue.put(cell)

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
    argp.add_argument(
        "-c", "--config-dir", default=os.path.join(os.path.expanduser("~"), ".nanb")
    )
    argp.add_argument("-L", "--server-log-file", default="nanb_server.log")

    subp = argp.add_subparsers(dest="command", required=True)

    subp_run = subp.add_parser("run")
    subp_run.add_argument("file")

    args = argp.parse_args()

    if not os.path.exists(args.config_dir):
        sys.stderr.write(
            f"ERROR: Config directory '{args.config_dir}' does not exist\n"
        )
        sys.exit(1)
        return

    load_config(args.config_dir)

    # FIXME: This is dumb, but textual lacks support for dynamic bindings it seems,
    # although there does appear to be a fix in the works, for now we'll
    # just shove it in here.
    # The rest of what would usually be in App, is in AppLogic
    class App(textual.app.App, AppLogic):

        BINDINGS = [
            # Binding(key="ctrl+s", action="save", description="Save output 💾"),
            Binding(
                key=C.keybindings["copy"],
                action="",
                description=C.tr["action_copy"],
                show=False,
            ),
            Binding(
                key=C.keybindings["clear_all"],
                action="clear_all",
                description=C.tr["action_clear_all"],
                show=False,
            ),
            Binding(
                key=C.keybindings["clear_cell_output"],
                action="clear_cell_output",
                description=C.tr["action_clear_cell_output"],
                show=False,
            ),
            Binding(
                key=C.keybindings["interrupt"],
                action="interrupt",
                description=C.tr["action_interrupt"],
            ),
            Binding(
                key=C.keybindings["restart_kernel"],
                action="restart_kernel",
                description=C.tr["action_restart_kernel"],
            ),
            Binding(
                key=C.keybindings["quit"],
                action="quit",
                description=C.tr["action_quit"],
            ),
            Binding(
                key=C.keybindings["run_all"],
                action="run_all",
                description=C.tr["action_run_all"],
            ),
            Binding(
                key="enter",
                action="run_cell",
                description=C.tr["action_run_cell"],
                show=False,
            ),
            Binding(key="h", action="help", description=C.tr["action_help"]),
        ]

        def __init__(self, cells, server_log_file, filename, *args, **kwargs):
            AppLogic.__init__(self, cells, server_log_file, filename)
            textual.app.App.__init__(self, *args, **kwargs)

        def compose(self) -> textual.app.ComposeResult:
            return self._compose()

    if args.command == "run":
        with open(args.file) as f:
            source = f.read()
            cells = split_to_cells(source)
            App(cells, args.server_log_file, args.file).run()
    else:
        sys.stderr.write(f"ERROR: Unknown command '{args.command}'\n")


if __name__ == "__main__":
    main()
