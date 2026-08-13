import time

import psutil
from textual.app import App
from textual.widgets import Footer, RichLog, Static

from purrge import __version__, awake
from purrge.cleaners import is_admin, run_all
from purrge.config import save


def fmt_mb(nbytes):
    return f"{nbytes / 1048576:.1f} mb"


def bar(pct, width=24):
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


class purrgeapp(App):
    TITLE = "purrge"
    CSS = """
    Screen { background: #1e1e2e; color: #cdd6f4; }
    #header { height: 3; padding: 1 2; background: #181825; }
    #status { height: 3; padding: 1 2; background: #313244; }
    #gauges { height: 4; padding: 1 2; }
    #log { border: round #45475a; background: #181825; padding: 0 1; }
    Footer { background: #181825; }
    """
    BINDINGS = [
        ("c", "clean_now", "clean now"),
        ("a", "toggle_awake", "keep-awake"),
        ("+", "interval_up", "interval +5"),
        ("-", "interval_down", "interval -5"),
        ("q", "quit", "quit"),
    ]

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.started = time.monotonic()
        self.total_freed = 0
        self.next_clean = time.monotonic() + cfg.interval_minutes * 60
        self.cleaning = False

    def compose(self):
        yield Static(id="header")
        yield Static(id="status")
        yield Static(id="gauges")
        yield RichLog(id="log", markup=True, wrap=True)
        yield Footer()

    def on_mount(self):
        awake.enable()
        self.set_interval(1.0, self.tick)
        self.logline(f"[#cba6f7]purrge v{__version__}[/] started, keep-awake on")
        if self.cfg.cleaners.get("ram_standby") and not is_admin():
            self.logline("[#fab387]not running as admin, ram standby clean will be skipped[/]")
        self.tick()

    def tick(self):
        up = int(time.monotonic() - self.started)
        hours, rem = divmod(up, 3600)
        minutes, seconds = divmod(rem, 60)
        remain = max(0, int(self.next_clean - time.monotonic()))
        rmin, rsec = divmod(remain, 60)
        badge = "[#a6e3a1]● on[/]" if awake.is_active() else "[#f38ba8]● off[/]"
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        self.query_one("#header", Static).update(
            f"[bold #cba6f7]purrge[/] [#6c7086]v{__version__}[/]   [#a6adc8]uptime {hours:02}:{minutes:02}:{seconds:02}[/]"
        )
        self.query_one("#status", Static).update(
            f"keep-awake {badge}   [#a6adc8]next clean[/] [#b4befe]{rmin:02}:{rsec:02}[/]   "
            f"[#a6adc8]interval[/] [#b4befe]{self.cfg.interval_minutes}m[/]   "
            f"[#a6adc8]freed[/] [#a6e3a1]{fmt_mb(self.total_freed)}[/]"
        )
        self.query_one("#gauges", Static).update(
            f"[#a6adc8]cpu[/] [#fab387]{bar(cpu)}[/] {cpu:4.0f}%\n"
            f"[#a6adc8]ram[/] [#cba6f7]{bar(ram)}[/] {ram:4.0f}%"
        )
        if remain == 0 and not self.cleaning:
            self.action_clean_now()

    def logline(self, message):
        self.query_one("#log", RichLog).write(f"[#6c7086]{time.strftime('%H:%M:%S')}[/] {message}")

    def action_clean_now(self):
        if self.cleaning:
            return
        self.cleaning = True
        self.logline("[#fab387]cleaning...[/]")
        self.run_worker(self.do_clean, thread=True)

    def do_clean(self):
        results = run_all(self.cfg)
        self.call_from_thread(self.finish_clean, results)

    def finish_clean(self, results):
        for r in results:
            self.total_freed += r.freed_bytes
            detail = f"freed {fmt_mb(r.freed_bytes)}, {r.items} items"
            if r.skipped:
                detail += f", {r.skipped} skipped"
            if r.errors:
                self.logline(f"[#f38ba8]{r.name}: failed[/]")
            else:
                self.logline(f"[#a6e3a1]{r.name}:[/] {detail}")
        self.next_clean = time.monotonic() + self.cfg.interval_minutes * 60
        self.cleaning = False
        self.logline("[#a6e3a1]clean done[/]")

    def action_toggle_awake(self):
        if awake.is_active():
            awake.disable()
            self.logline("[#f38ba8]keep-awake off[/]")
        else:
            awake.enable()
            self.logline("[#a6e3a1]keep-awake on[/]")

    def action_interval_up(self):
        self.set_clean_interval(self.cfg.interval_minutes + 5)

    def action_interval_down(self):
        self.set_clean_interval(self.cfg.interval_minutes - 5)

    def set_clean_interval(self, minutes):
        minutes = max(5, min(240, minutes))
        if minutes == self.cfg.interval_minutes:
            return
        self.next_clean += (minutes - self.cfg.interval_minutes) * 60
        self.cfg.interval_minutes = minutes
        save(self.cfg)
        self.logline(f"interval set to [#b4befe]{minutes}m[/]")
