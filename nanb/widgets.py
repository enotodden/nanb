from textual.widget import Widget
from textual.widgets import Markdown, Label, Static, Log
from textual.app import ComposeResult
from textual.events import Click
from textual.reactive import var
from rich.syntax import Syntax
import rich.spinner

from nanb.cell import Cell

class Segment(Widget):
    """
    Base class for a code or markdown segment
    """

    can_focus = True
    focusable = True

    state = var("")

    def __init__(self, idx: int, cell: Cell, **kwargs):
        self.idx = idx
        self.cell = cell
        self.label = None
        super().__init__(**kwargs)

    def on_click(self, event: Click) -> None:
        self.focus()
        if getattr(self, "on_clicked", None):
            self.on_clicked(self)

    def watch_state(self, value):
        if self.label:
            self.label.update(self.make_label_text())

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

class MarkdownSegment(Segment):
    """
    A cell segment that renders markdown
    """

    def compose(self) -> ComposeResult:
        assert self.cell.cell_type == "markdown"
        self.label = Label(self.make_label_text(), classes="celllabel")
        self.content = Markdown(
            self.cell.source,
            classes='markdowncell',
            id=f"cell_{self.idx}"
        )
        yield self.label
        yield self.content

class CodeSegment(Segment):
    """
    A cell segment that renders code
    """

    def compose(self) -> ComposeResult:
        self.label = Label(self.make_label_text(), classes="celllabel")
        self.content = Static(renderable=Syntax(
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


class Spinner(Static):
    """
    Spinner that will start and stop based on wether code is running

    Borrowed from this lovely blog post by Rodrigo Girão Serrão:
        https://textual.textualize.io/blog/2022/11/24/spinners-and-progress-bars-in-textual/
    """
    DEFAULT_CSS = """
    Spinner {
        content-align: right middle;
        height: auto;
        padding-right: 1;
    }
    """
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(**kwargs)
        self.style = "point"
        self._renderable_object = rich.spinner.Spinner(self.style)

    def update_rendering(self) -> None:
        self.update(self._renderable_object)

    def on_mount(self) -> None:
        self.interval_update = self.set_interval(1 / 60, self.update_rendering)

    def pause(self) -> None:
        self.interval_update.pause()

    def resume(self) -> None:
        self.interval_update.resume()


class Output(Log):
    """
    A widget that displays the output of a cell
    """

    def on_click(self, event: Click) -> None:
        self.focus()

    def use_cell(self, cell: Cell):
        if cell is None:
            self.clear()
            return
        self.clear()
        self.write(cell.output)
