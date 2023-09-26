import os
from dataclasses import dataclass

@dataclass
class Config:
    css: str

def read_config(path: str) -> Config:
    if not os.path.exists(path):
        return Config(css=None)
    css = None
    if os.path.exists(os.path.join(path, "nanb.css")):
        path = os.path.join(path, "nanb.css")
        css = open(path).read()
    return Config(css=css)
