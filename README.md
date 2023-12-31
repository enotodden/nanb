nanb - Not A NoteBook
=====================

Jupyter-style execution with plain Python files, in the terminal.

![screenshot](https://github.com/enotodden/nanb/blob/09570785cb135ccbb74ba787f1177b54639786d2/nanb_screenshot.png)

Example:

```python

# My Notebook
# ===========
#
# Welcome to my **not-a-notebook**!
#
# Here is a description, and some bullet points:
# - foo
# - bar
# - baz
#
# Here is a code block:
# ```python
# print("hello world")
# ```
#
# Here is a table:
# | foo | bar |
# |-----|-----|
# | 1   | 2   |
# | 3   | 4   |
#


# --- Do some imports
import os
import json


# --- Set a var
hello_abc = "Hello ABC!"

# --- Print it
print(hello_abc)

# ---
# This cell has no name, which is also fine
print("Hello world")
```

## Installation

```shell
$ pip install nanb
```


## Running a file

```shell
$ nanb run ./myfile.py
```

## Why?

Jupyter notbooks are great, but they are not regular Python files, and can be hard to work with in your editor of choice.

This project is an attempt at providing a stateful REPL-like execution environment for vanilla Python,
in the terminal, with regular source files that you edit using the editor/IDE of your choice.

## Cell syntax

Like in jupyter, a file used in nanb is divided into cells that can be executed independently.

Code cells are marked using `# ---`
```python
# ---
print('Hello world')
```

Markdown cells are just regular comments using `# %%%` to indicate their beginning:
```python
# %%%
# ## This is an H2 
# - These
# - Are 
# - List 
# - Items
```

Code cells can also have labels:

```python
# --- Do stuff
do_stuff()
```

## Configuring nanb

nanb can be configured by adding a toml configuration file in `$HOME/.nanb/nanb.toml`.

### Default config:

```

cell_name_max = 20

[keybindings]
quit = "q"
restart_kernel = "ctrl+r"
copy = "y"
clear_cell_output = "c"
interrupt = "i"
run_all = "ctrl+a"
clear_all = "ctrl+x"

[server]
log_file = "/tmp/nanb_server.log"
socket_prefix = "/tmp/nanb_socket_"

[code]
theme = "github-dark"
background = "#1a1a1a"

[output]
theme = "vscode_dark"
line_numbers = false

[tr]
action_quit = "Quit"
action_restart_kernel = "Restart Kernel"
action_copy = "Copy"
action_clear_cell_output = "Clear Cell Output"
action_interrupt = "Interrupt"
action_help = "Help"
action_run_cell = "Run Cell"
action_run_all = "Run All"
action_clear_all = "Clear All"
action_close = "Close"
state_running = "RUNNING"
state_pending = "PENDING"
dh_keybindings = "Keybindings"
dh_key = "Key"
dh_action = "Action"
kb_quit = "Quit the application"
kb_restart_kernel = "Restart the kernel"
kb_copy = "Copy selected output"
kb_clear_cell_output = "Clear the output of the current cell"
kb_interrupt = "Interrupt the current execution"
kb_run_cell = "Run the current cell"
kb_run_all = "Run all cells"
kb_clear_all = "Clear all cells"
kb_help = "Show this help screen"
kb_arrows = "Move between cells"
kb_close_help = "Close the help screen"

```


### Config options:

- `server`: Config options for the server/kernel that actually runs your code.
    - `log_file`: Specifies where to write the server log to.
    - `prefix`: Sets where to put the socket file the main application uses to communicate with the server.
- `code`: Settings for displaying code.
    - `theme`: Pygments theme used to render code. See https://pygments.org/demo/ for available options.
    - `background`: The background color used for code cells.
- `output`: Settings for the output pane.
    - `theme`: Available options: `'dracula', 'github_light', 'monokai', 'vscode_dark'`.
    - `line_numbers`: Wether to display line numbers in the output.
- `keybindings`:
    - `quit`: Key combination used to quit the application.
    - `restart_kernel`: Key combination used to kill the code execution server and start a new one.
    - `copy`: Key combination used to copy selected text from the output.
    - `clear_cell_output`: Key combination used to clear a single cell of output.
    - `interrupt`: Key combination used to interrupt current execution.
    - `run_all`: Run all cells.
    - `clear_all:` = Clear output from all cells.
- `tr`: Strings/translations used to render state info and help text.
- `cell_name_max`: Sets the max number of characters cell names/labels are displayed with.


### Custom CSS:
Since nanb uses textual, it is also possible to override the looks using custom CSS.

If the file `~/.nanb/nanb.css` exists, it's content will be appended to the default css on startup.

See https://textual.textualize.io/guide/CSS/ for more information.



## Q&A

### Does nanb support editing code?

No. The idea is providing an environment for execution, letting you use your own editor to write code.

### Does nanb support jupyter style magic?

No, as that would make your files behave differently in nanb vs running your files using the regular python commmand.
