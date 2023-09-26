class Cell:
    cell_type = None

    def __init__(self, cell_name, source, line_start, line_end):
        self.source = source
        self.line_start = line_start
        self.line_end = line_end
        self.current_output = ""
        self.name = cell_name

    def __str__(self):
        source_numbered = "\n".join([f"{self.line_start+i+1} {line}" for i, line in enumerate(self.source.split("\n"))])
        return f"<{self.__class__.__name__} {self.line_start}-{self.line_end}:\n{source_numbered}\n>"

    def __repr__(self):
        return str(self)

class MarkdownCell(Cell):
    cell_type = "markdown"

class CodeCell(Cell):
    cell_type = "code"
