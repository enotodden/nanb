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
from nanb.config import (
    Config,
    read_config,
    load_config,
    C,
    config_toml,
    default_config_toml,
)
from nanb.client import UnixDomainClient
from nanb.server_manager import ServerManager
from nanb.help_screen import HelpScreen
from nanb.parser import load_file

from nanb.widgets import (
    MarkdownSegment,
    CodeSegment,
    Output,
    FooterWithSpinner,
    CellList,
)

THIS_DIR = os.path.dirname(os.path.abspath(__file__))


CSS = open(os.path.join(THIS_DIR, "nanb.css")).read()


class AppLogic:
    def __init__(self, cells, filename, *args, **kwargs):
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
        try:
            new_cells = load_file(self.filename)
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
        "-C", "--config-dir", default=os.path.join(os.path.expanduser("~"), ".nanb")
    )
    argp.add_argument(
        "-c",
        "--config",
        nargs=2,
        metavar=("path", "value"),
        action="append",
        default=[],
        help="Set config options by path and value",
    )

    subp = argp.add_subparsers(dest="command", required=True, help="Command")

    subp_run = subp.add_parser("run", help="Run a file")
    subp_run.add_argument("file", help="File to run")

    subp_default_config = subp.add_parser(
        "default-config", help="Print the default config"
    )
    subp_default_config = subp.add_parser("config", help="Print the current config")

    args = argp.parse_args()

    if not os.path.exists(args.config_dir):
        sys.stderr.write(
            f"ERROR: Config directory '{args.config_dir}' does not exist\n"
        )
        sys.exit(1)
        return

    load_config(args.config_dir)

    for path, val in args.config:
        C.set_by_path(path, val)

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

        def __init__(self, cells, filename, *args, **kwargs):
            AppLogic.__init__(self, cells, filename)
            textual.app.App.__init__(self, *args, **kwargs)

        def compose(self) -> textual.app.ComposeResult:
            return self._compose()

    if args.command == "run":
        if not os.path.exists(args.file):
            sys.stderr.write(f"ERROR: File '{args.file}' does not exist\n")
            sys.stderr.flush()
            exit(1)
            return
        cells = load_file(args.file)
        App(cells, args.file).run()
    elif args.command == "default-config":
        print(default_config_toml())
    elif args.command == "config":
        print(config_toml())
    else:
        sys.stderr.write(f"ERROR: Unknown command '{args.command}'\n")
        sys.stderr.flush()
        exit(1)


if __name__ == "__main__":
    main()
