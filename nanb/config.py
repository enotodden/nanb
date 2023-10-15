import os
import copy
from dataclasses import dataclass, field

import toml

DEFAULT_KEYBINDINGS = {
    "quit": "q",
    "restart_kernel": "ctrl+r",
    "copy": "y",
    "clear_cell_output": "c",
    "interrupt": "i",
}

DEFAULT_SERVER_LOG_FILE = "/tmp/nanb_server.log"

DEFAULT_TR = {
    "action_quit": "Quit",
    "action_restart_kernel": "Restart Kernel",
    "action_copy": "Copy",
    "action_clear_cell_output": "Clear Cell Output",
    "action_interrupt": "Interrupt",
    "state_running": "RUNNING",
    "state_pending": "PENDING",
}

DEFAULT_SOCKET_PREFIX = "/tmp/nanb_socket_"

DEFAULT_CODE_THEME = "github-dark"

DEFAULT_CODE_BACKGROUND = "#1a1a1a"

DEFAULT_CELL_NAME_MAX = 20

DEFAULT_OUTPUT_THEME = "vscode_dark"
DEFAULT_OUTPUT_LINE_NUMBERS = False

@dataclass
class Config:
    css: str                 = None
    keybindings: dict        = field(default_factory=lambda: copy.deepcopy(DEFAULT_KEYBINDINGS))
    server_log_file: str     = DEFAULT_SERVER_LOG_FILE
    socket_prefix: str       = DEFAULT_SOCKET_PREFIX
    tr: dict                 = field(default_factory=lambda: copy.deepcopy(DEFAULT_TR))
    code_theme: str          = DEFAULT_CODE_THEME
    code_background: str     = DEFAULT_CODE_BACKGROUND
    cell_name_max: int       = DEFAULT_CELL_NAME_MAX
    output_theme: str        = DEFAULT_OUTPUT_THEME
    output_line_numbers: bool = DEFAULT_OUTPUT_LINE_NUMBERS


def read_config(path: str) -> Config:
    if not os.path.exists(path):
        return Config(css=None)
    css = None
    if os.path.exists(os.path.join(path, "nanb.css")):
        csspath = os.path.join(path, "nanb.css")
        css = open(csspath).read()

    c = Config(css=css)

    if os.path.exists(os.path.join(path, "nanb.toml")):
        with open(os.path.join(path, "nanb.toml")) as f:
            cfg = toml.load(f)

            if "keybindings" in cfg:
                for k, v in cfg["keybindings"].items():
                    if k not in DEFAULT_KEYBINDINGS.keys():
                        raise Exception(f"Unsupported keybinding: {k}")
                    c.keybindings[k] = v

            if "server" in cfg:
                server = cfg["server"]
                c.server_log_file = server.get("log_file", DEFAULT_SERVER_LOG_FILE)
                c.socket_prefix = server.get("socket_prefix", DEFAULT_SOCKET_PREFIX)

            if "tr" in cfg:
                for k, v in cfg["tr"].items():
                    if k not in DEFAULT_TR.keys():
                        raise Exception(f"Unsupported translation: {k}")
                    c.tr[k] = v

            if "code" in cfg:
                code = cfg["code"]
                c.code_theme = code.get("theme", DEFAULT_CODE_THEME)
                c.code_background = code.get("background", DEFAULT_CODE_BACKGROUND)

            c.cell_name_max = cfg.get("cell_name_max", DEFAULT_CELL_NAME_MAX)

            if "output" in cfg:
                output = cfg["output"]
                c.output_theme = output.get("theme", DEFAULT_OUTPUT_THEME)
                c.output_line_numbers = output.get("line_numbers", DEFAULT_OUTPUT_LINE_NUMBERS)

    return c


C = Config()

def load_config(path: str):
    c = read_config(path)
    for k, _ in C.__annotations__.items():
        setattr(C, k, getattr(c, k))


if __name__ == "__main__":
    out = dict(
        keybindings=DEFAULT_KEYBINDINGS,
        server=dict(
            log_file=DEFAULT_SERVER_LOG_FILE,
            socket_prefix=DEFAULT_SOCKET_PREFIX,
        ),
        code=dict(
            theme=DEFAULT_CODE_THEME,
            background=DEFAULT_CODE_BACKGROUND,
        ),
        output=dict(
            theme=DEFAULT_OUTPUT_THEME,
            line_numbers=DEFAULT_OUTPUT_LINE_NUMBERS,
        ),
        tr=DEFAULT_TR,
        cell_name_max=DEFAULT_CELL_NAME_MAX,
    )
    print(toml.dumps(out))
