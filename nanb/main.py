import os
import sys
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
from textual.reactive import reactive

from nanb.cell import Cell, MarkdownCell, CodeCell
from nanb.config import Config, read_config
from nanb.client import UnixDomainClient

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

class TUICellSegment(textual.widget.Widget):
    can_focus = True
    focusable = True

    output_text = textual.reactive.var("")
    state = textual.reactive.var("")
    cell = textual.reactive.var(None)

    def __init__(self, idx:int, cell: Cell, **kwargs):
        self.idx = idx
        self.cell = cell
        self.label = None
        super().__init__(**kwargs)

    def make_label_text(self):
        state = self.state
        if state != "":
            state = f" - [{state}]"
        if self.cell.name is not None:
            cellname = self.cell.name
            if len(cellname) > 20:
                cellname = cellname[:20] + "..."
            return f"{cellname} - {self.idx+1}{state}"
        return f"{self.idx+1}{state}"

    def compose(self) -> textual.app.ComposeResult:
        self.label = textual.widgets.Label(self.make_label_text(), classes="celllabel")
        if self.cell.cell_type == "markdown":
            self.content = textual.widgets.Markdown(self.cell.source, classes='markdowncell', id=f"cell_{self.idx}")
        elif self.cell.cell_type == "code":
            self.content = textual.widgets.Static(renderable=rich.syntax.Syntax(
                self.cell.source,
                "python",
                line_numbers=True,
                start_line=self.cell.line_start,
                word_wrap=False,
                indent_guides=True,
                theme="github-dark",
            ), classes='codecell', id=f"cell_{self.idx}")
        yield self.label
        yield self.content

    def on_click(self, event: textual.events.Click) -> None:
        self.focus()
        if getattr(self, "on_clicked", None):
            self.on_clicked(self)

    def watch_state(self, value):
        if self.label:
            self.label.update(self.make_label_text())

CSS = open(os.path.join(THIS_DIR, "nanb.css")).read()

class App(textual.app.App):

    def __init__(self, config: Config, cells, client, filename, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_running_code = False
        self.output = None
        self.CSS = CSS
        if config.css:
            self.CSS += "\n" + config.css
        self.cells = cells
        self.client = client
        self.filename = filename

    def on_segment_clicked(self, w):
        self.currently_focused = w.idx
        self.widgets[self.currently_focused].focus()
        self.output.clear()
        self.output.write(w.output_text)

    def compose(self) -> textual.app.ComposeResult:
        widgets = []
        with textual.containers.Container(id="app-grid"):
            with textual.containers.VerticalScroll(id="notebook"):
                for i, cell in enumerate(self.cells):
                    classes = "segment"
                    if i == len(self.cells)-1:
                        classes += " last"
                    w = TUICellSegment(i, cell, classes=classes, id=f"segment_{i}")
                    w.on_clicked = self.on_segment_clicked
                    widgets.append(w)
                    yield w
            with textual.containers.Container(id="output"):
                self.output = textual.widgets.Log()
                self.output.on_click = lambda self: self.focus()
                yield self.output
        self.widgets = widgets


    def on_mount(self):
        self.currently_focused = 0
        self.widgets[self.currently_focused].focus()

    @textual.work()
    async def run_code(self):
        loop = asyncio.get_event_loop()
        w = self.widgets[self.currently_focused]
        if w.cell.cell_type != "code":
            return
        w.output_text = ""
        w.state = "PENDING"
        # create task
        q = asyncio.Queue()
        task = loop.create_task(self.client.run_code(w.cell.line_start, w.cell.source, q))

        started = False

        while not task.done():
            print("waiting for task")
            try:
                result = await asyncio.wait_for(q.get(), timeout=0.2)
                if not result:
                    continue
                if not started:
                    started = True
                    w.output_text = ""
                    w.state = "RUNNING"
                w.output_text+=result

                wcur = self.widgets[self.currently_focused]
                self.output.clear()
                self.output.write(wcur.output_text)
            except asyncio.TimeoutError:
                pass

        w.state = ""

    async def on_key(self, event: textual.events.Key) -> None:
        if event.key == "up":
            if self.currently_focused > 0:
                self.currently_focused -= 1
                w = self.widgets[self.currently_focused]
                w.focus()
                self.output.clear()
                self.output.write(w.output_text)
        elif event.key == "down":
            if self.currently_focused < len(self.widgets) - 1:
                self.currently_focused += 1
                w = self.widgets[self.currently_focused]
                w.focus()
                self.output.clear()
                self.output.write(w.output_text)
        if event.key == "enter":
            self.run_code()


def main():
    argp = argparse.ArgumentParser()
    argp.add_argument("-c", "--config-dir", default=os.path.join(os.path.expanduser("~"), ".nanb"))
    argp.add_argument("-L", "--server-log-file", default="/tmp/nanb_server.log")

    subp = argp.add_subparsers(dest='command', required=True)

    subp_run = subp.add_parser("run")
    subp_run.add_argument("file")

    args = argp.parse_args()

    if not os.path.exists(args.config_dir):
        sys.stderr.write(f"ERROR: Config directory '{args.config_dir}' does not exist\n")
        sys.exit(1)
        return

    socket_uuid = uuid.uuid4().hex
    socket_file = "/tmp/nanb_socket_" + socket_uuid

    config = read_config(args.config_dir)

    server_log_file = open(args.server_log_file, "w")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    server = subprocess.Popen([sys.executable, "-m", "nanb.server", "--socket-file", socket_file], stdout=server_log_file, stderr=server_log_file, env=env)

    client = UnixDomainClient(socket_file)

    if args.command == "run":
        with open(args.file) as f:
            source = f.read()
            cells = split_to_cells(source)
            App(config, cells, client, args.file).run()
    else:
        sys.stderr.write(f"ERROR: Unknown command '{args.command}'\n")

    server.terminate()
    server.wait()

if __name__ == "__main__":
    main()
