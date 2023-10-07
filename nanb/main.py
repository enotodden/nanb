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
import rich.spinner
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

def load_file(filename: str) -> [Cell]:
    with open(filename, "r") as f:
        return split_to_cells(f.read())


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
                word_wrap=True,
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
            w = TUICellSegment(i, cell, classes=classes, id=f"segment_{i}")
            w.on_clicked = self.on_segment_clicked
            widgets.append(w)
        return widgets

    def compose(self) -> textual.app.ComposeResult:
        widgets = self.make_widgets()
        self.widgets = widgets
        for w in widgets:
            yield w

    def on_segment_clicked(self, w):
        self.currently_focused = w.idx
        self.widgets[self.currently_focused].focus()
        self.on_output(w.output_text)

    def on_mount(self):
        self.currently_focused = 0
        self.widgets[self.currently_focused].focus()

    async def on_key(self, event: textual.events.Key) -> None:
        if event.key == "up":
            if self.currently_focused > 0:
                self.currently_focused -= 1
                w = self.widgets[self.currently_focused]
                w.focus()
                self.on_output(w.output_text)
        elif event.key == "down":
            if self.currently_focused < len(self.widgets) - 1:
                self.currently_focused += 1
                w = self.widgets[self.currently_focused]
                w.focus()
                self.on_output(w.output_text)

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
        self.currently_focused = 0
        self.widgets[self.currently_focused].focus()



CSS = open(os.path.join(THIS_DIR, "nanb.css")).read()


class ServerManager:

    def __init__(self, server_log_file):
        self.socket_file = None
        self.server_log_file = server_log_file

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
        server.terminate()
        server.wait()

    def restart(self):
        self.stop()
        self.start()

class SpinnerWidget(textual.widgets.Static):
    """
    Spinner that will start and stop based on wether code is running

    Borrowed from this lovely blog post by Rodrigo Girão Serrão:
        https://textual.textualize.io/blog/2022/11/24/spinners-and-progress-bars-in-textual/
    """
    DEFAULT_CSS = """
    SpinnerWidget {
        content-align: right middle;
        margin-right: 2;
        height: auto;
    }
    """
    def __init__(self, style: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.style = style
        self._renderable_object = rich.spinner.Spinner(style)

    def update_rendering(self) -> None:
        self.update(self._renderable_object)

    def on_mount(self) -> None:
        self.interval_update = self.set_interval(1 / 60, self.update_rendering)

    def pause(self) -> None:
        self.interval_update.pause()

    def resume(self) -> None:
        self.interval_update.resume()

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
        self.task_queue = asyncio.Queue()

    def on_output(self, text):
        self.output.clear()
        self.output.write(text)

    def on_mount(self):
        self.spinner.pause()

    def compose(self) -> textual.app.ComposeResult:
        self.spinner = SpinnerWidget("point", id="spin")
        yield self.spinner
        with textual.containers.Container(id="app-grid"):
            self.cellsw = Cells(self.cells, id="cells")
            self.cellsw.on_output = self.on_output
            self.cellsw.on_run_code = self.run_code
            yield self.cellsw
            with textual.containers.Container(id="output"):

                self.output = textual.widgets.Log()
                self.output.on_click = lambda self: self.focus()
                yield self.output

        loop = asyncio.get_event_loop()
        self.process_task_queue_task = asyncio.create_task(self.process_task_queue())

    async def process_task_queue(self):
        while True:
            w = await self.task_queue.get()
            loop = asyncio.get_event_loop()
            #w = self.widgets[self.currently_focused]
            w.output_text = ""
            w.state = "RUNNING"
            # create task
            q = asyncio.Queue()
            task = loop.create_task(self.client.run_code(w.cell.line_start, w.cell.source, q))

            started = False

            self.spinner.resume()
            while not task.done():
                try:
                    result = await asyncio.wait_for(q.get(), timeout=0.2)
                    if not result:
                        continue
                    if not started:
                        started = True
                        w.output_text = ""
                        w.state = "RUNNING"
                    w.output_text += result

                    self.output.clear()
                    if self.cellsw.current:
                        self.output.write(self.cellsw.current.output_text)

                except asyncio.TimeoutError:
                    pass
            self.spinner.pause()
            w.state = ""

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

     # This is just a placeholder for what we want to do later on file
     # reload
#    async def on_key(self, event: textual.events.Key) -> None:
#        if event.key == "u":
#            await self.cellsw.refresh_cells(self.cells)
#            self.output.write(self.cellsw.current.output_text)
#            self.clear_task_queue()


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
