import uuid
import hashlib

class Cell:
    cell_type = None

    def __init__(self, cell_name, source, line_start, line_end):
        self.source = source
        self.line_start = line_start
        self.line_end = line_end
        self.output = ""
        self.name = cell_name
        self.id = uuid.uuid4().hex

    def __str__(self):
        source_numbered = "\n".join([f"{self.line_start+i+1} {line}" for i, line in enumerate(self.source.split("\n"))])
        return f"<{self.__class__.__name__} {self.line_start}-{self.line_end}:\n{source_numbered}\n>"

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        return self.id == other.id

    def nsh(self):
        """
        Returns the "normalized source hash" in order to compare cells
        with each other.
        Ideally this would go deeper than just stripping whitespace and hashing
        the source. TBD.
        """
        hash_input = self.source.strip()
        return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

class MarkdownCell(Cell):
    cell_type = "markdown"

class CodeCell(Cell):
    cell_type = "code"

def match_cells(old_cells: [Cell], new_cells: [Cell]):
    for nc in new_cells:
        for oc in old_cells:
            if nc.nsh() == oc.nsh():
                nc.output = oc.output
                break
