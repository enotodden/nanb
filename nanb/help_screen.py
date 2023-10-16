from textual.screen import Screen
from textual.binding import Binding
from textual.widgets import MarkdownViewer


class HelpScreen(Screen):
    """
    Implements the help screen
    """

    BINDINGS = [
        Binding(key="escape", action="esc", description="Close"),
        Binding(key="h", action="esc", description="Close"),
    ]

    def compose(self):
        """
        Render markdown help text generated using config
        """
        mdv = MarkdownViewer(C.help_md(), show_table_of_contents=True)

        # FIXME: Links in textual raises an exception, as they are treated as
        #        file paths, so just nop out the function that causes trouble for now.
        async def nop_linkclick(*args):
            pass

        mdv.go = nop_linkclick

        yield mdv

    def action_esc(self):
        """Exit help screen"""
        self.app.pop_screen()
