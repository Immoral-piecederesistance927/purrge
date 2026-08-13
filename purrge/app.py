import sys

from purrge import __version__, awake
from purrge.config import load, save


def fmt_mb(nbytes):
    return f"{nbytes / 1048576:.1f} mb"


def run_headless(cleaners=None, path=None):
    from rich.console import Console
    from rich.table import Table

    from purrge.cleaners import run_all

    console = Console()
    console.print(f"[bold #cba6f7]purrge[/] [#6c7086]v{__version__}[/] [#fab387]cleaning...[/]")
    cfg = load(path)
    results = run_all(cfg, cleaners)
    table = Table(border_style="#45475a", header_style="#a6adc8", show_edge=True)
    table.add_column("cleaner", style="#cdd6f4")
    table.add_column("freed", justify="right", style="#a6e3a1")
    table.add_column("items", justify="right", style="#b4befe")
    table.add_column("status", style="#a6adc8")
    freed = 0
    for r in results:
        freed += r.freed_bytes
        if r.errors:
            status = "[#f38ba8]failed[/]"
        elif r.skipped and not r.items:
            status = "[#fab387]skipped[/]"
        else:
            status = "[#a6e3a1]ok[/]"
        table.add_row(r.name, fmt_mb(r.freed_bytes), str(r.items), status)
    console.print(table)
    cfg.total_freed_bytes += freed
    save(cfg, path)
    console.print(
        f"[#a6adc8]freed[/] [bold #a6e3a1]{fmt_mb(freed)}[/]   "
        f"[#a6adc8]all-time[/] [#cba6f7]{fmt_mb(cfg.total_freed_bytes)}[/]"
    )
    return results


def main():
    args = sys.argv[1:]
    if "--version" in args:
        print(f"purrge {__version__}")
        return
    if args and args[0] == "clean":
        run_headless()
        return
    from purrge.ui import purrgeapp
    cfg = load()
    try:
        purrgeapp(cfg).run()
    finally:
        awake.disable()
