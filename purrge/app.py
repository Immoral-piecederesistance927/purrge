import sys

from purrge import __version__, awake
from purrge.config import load


def main():
    if "--version" in sys.argv:
        print(f"purrge {__version__}")
        return
    from purrge.ui import purrgeapp
    cfg = load()
    try:
        purrgeapp(cfg).run()
    finally:
        awake.disable()
