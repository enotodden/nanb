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
    "run_all": "ctrl+a",
    "clear_all": "ctrl+x",
}

DEFAULT_SERVER_LOG_FILE = "/tmp/nanb_server.log"

DEFAULT_TR = {
    "action_quit": "Quit",
    "action_restart_kernel": "Restart Kernel",
    "action_copy": "Copy",
    "action_clear_cell_output": "Clear Cell Output",
    "action_interrupt": "Interrupt",
    "action_help": "Help",
    "action_run_cell": "Run Cell",
    "action_run_all": "Run All",
    "action_clear_all": "Clear All",
    # For closing the help screen
    "action_close": "Close",
    "state_running": "RUNNING",
    "state_pending": "PENDING",
    "dh_keybindings": "Keybindings",
    "dh_key": "Key",
    "dh_action": "Action",
    "kb_quit": "Quit the application",
    "kb_restart_kernel": "Restart the kernel",
    "kb_copy": "Copy selected output",
    "kb_clear_cell_output": "Clear the output of the current cell",
    "kb_interrupt": "Interrupt the current execution",
    "kb_run_cell": "Run the current cell",
    "kb_run_all": "Run all cells",
    "kb_clear_all": "Clear all cells",
    "kb_help": "Show this help screen",
    "kb_arrows": "Move between cells",
    "kb_close_help": "Close the help screen",
}

DEFAULT_SOCKET_PREFIX = "/tmp/nanb_socket_"

DEFAULT_CODE_THEME = "github-dark"

DEFAULT_CODE_BACKGROUND = "#1a1a1a"

DEFAULT_CELL_NAME_MAX = 20

DEFAULT_OUTPUT_THEME = "vscode_dark"
DEFAULT_OUTPUT_LINE_NUMBERS = False


@dataclass
class Config:
    css: str = None
    keybindings: dict = field(
        default_factory=lambda: copy.deepcopy(DEFAULT_KEYBINDINGS)
    )
    server_log_file: str = DEFAULT_SERVER_LOG_FILE
    socket_prefix: str = DEFAULT_SOCKET_PREFIX
    tr: dict = field(default_factory=lambda: copy.deepcopy(DEFAULT_TR))
    code_theme: str = DEFAULT_CODE_THEME
    code_background: str = DEFAULT_CODE_BACKGROUND
    cell_name_max: int = DEFAULT_CELL_NAME_MAX
    output_theme: str = DEFAULT_OUTPUT_THEME
    output_line_numbers: bool = DEFAULT_OUTPUT_LINE_NUMBERS

    def keybinding_docs(self) -> str:
        lines = []
        for k, v in self.keybindings.items():
            lines.append(f"| **{v}** | {self.tr['kb_' + k]} |")
        return "\n".join(lines)

    def help_md(self) -> str:
        return f"""
Help
====

Find more detailed information at https://github.com/enotodden/nanb

# {self.tr['dh_keybindings']}
| Key | Action |
| --- | ------ |
{self.keybinding_docs()}
|       |        |
| ⬆︎ / ⬇︎ | {self.tr['kb_arrows']} |
| ↵     | {self.tr['kb_run_cell']}  |
|       |        |
| h     | {self.tr['kb_help']} |
| h/ESC | {self.tr['kb_close_help']} |

# Syntax

### Code:

Starting the a line with `# ---` denotes a code block:

```python
# ---

print("Hello world")

```

### Markdown:

Starting the a line with `# %%%` denotes a Markdown block:

```python
# %%%
#
# My Notebook
# ===========
#
# Welcome to my **not-a-notebook**!
#
# - This
# - is
# - a
# - list
#
```

"""


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
                c.output_line_numbers = output.get(
                    "line_numbers", DEFAULT_OUTPUT_LINE_NUMBERS
                )

    return c


DEFAULT_CONFIG = Config()

C = Config()

def load_config(path: str):
    c = read_config(path)
    for k, _ in C.__annotations__.items():
        setattr(C, k, getattr(c, k))


def _config_toml(c: Config) -> str:
    out = dict(
        keybindings=c.keybindings,
        server=dict(
            log_file=c.server_log_file,
            socket_prefix=c.socket_prefix,
        ),
        code=dict(
            theme=c.code_theme,
            background=c.code_background,
        ),
        output=dict(
            theme=c.output_theme,
            line_numbers=c.output_line_numbers,
        ),
        tr=c.tr,
        cell_name_max=c.cell_name_max,
    )
    return toml.dumps(out)

def default_config_toml() -> str:
    return _config_toml(DEFAULT_CONFIG)

def config_toml():
    return _config_toml(C)

if __name__ == "__main__":
    print(default_config_toml())
