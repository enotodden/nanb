import subprocess

from textual.widget import Widget
from textual.widgets import Markdown, Label, Static, Log, Footer, TextArea
from textual.app import ComposeResult
from textual.events import Click
from textual.reactive import var
from textual.binding import Binding

from rich.syntax import Syntax
import rich.spinner
import rich.text
import rich.table

from nanb.cell import Cell
from nanb.config import C

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
            if len(cellname) > C.cell_name_max:
                cellname = cellname[:C.cell_name_max] + "..."
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
            theme=C.code_theme,
            background_color=C.code_background,
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

def write_to_clipboard(output):
    process = subprocess.Popen(
        'pbcopy', env={'LANG': 'en_US.UTF-8'}, stdin=subprocess.PIPE)
    process.communicate(output.encode('utf-8'))

class Output(TextArea):
    """
    A widget that displays the output of a cell
    """

    BINDINGS = [
        Binding(C.keybindings["copy"], "copy", C.tr["action_copy"]),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def action_copy(self):
        write_to_clipboard(self.selected_text)

    def on_mount(self):
        self.show_line_numbers = C.output_line_numbers
        self.theme = C.output_theme
        super().on_mount()

    def use_cell(self, cell: Cell):
        if cell is None:
            self.clear()
            return
        self.clear()
        self.write(cell.output)

    def replace(self, *args, **kwargs):
        """ Makes the textarea non-editable """
        return None

    def write(self, text):
        self._set_document(text, self.language)
        self._refresh_size()
        self.move_cursor((self.document.line_count - 1, 0))
        self.scroll_cursor_visible()



class FooterSpinner(rich.spinner.Spinner):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.paused = False

    def render(self, time: float):
        """
        Overrides the default spinner render in order to make the spinner
        stay put when scrolling and re-rendering occurs.
        Also ensures that the footer is right-aligned with the spinner on the
        right of the screen.
        Other than that it works exactly like the stock spinner's render method.
        """
        if self.start_time is None:
            self.start_time = time

        if self.paused:
            frame_no = 0
        else:
            frame_no = ((time - self.start_time) * self.speed) / (
                self.interval / 1000.0
            ) + self.frame_no_offset
        frame = rich.text.Text(
            self.frames[int(frame_no) % len(self.frames)], style=self.style or ""
        )

        if self._update_speed:
            self.frame_no_offset = frame_no
            self.start_time = time
            self.speed = self._update_speed
            self._update_speed = 0.0

        if not self.text:
            return frame
        elif isinstance(self.text, (str, rich.text.Text)):
            return rich.text.Text.assemble(self.text, " ", frame, " 🐍", justify="right")
        else:
            table = rich.table.Table.grid(padding=1)
            table.add_row(frame, self.text)
            return table

class FooterWithSpinner(Footer):

    def on_mount(self):
        if self._key_text is None:
            self._key_text = self._make_key_text()
        self.renderable = FooterSpinner("point", text=self._key_text)
        self.renderable.paused = True
        self.interval_update = self.set_interval(1 / 60, self.update_rendering)

    def pause_spinner(self):
        self.interval_update.pause()
        self.renderable.paused = True
        self.refresh(layout=True)

    def resume_spinner(self):
        self.interval_update.resume()
        self.renderable.paused = False

    def update_rendering(self):
        self.refresh(layout=True)

    def render(self):
        return self.renderable


