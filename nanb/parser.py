from nanb.cell import Cell, MarkdownCell, CodeCell, match_cells


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
