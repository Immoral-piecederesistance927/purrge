import json
import sys
import time
import urllib.request
from collections import deque

import psutil
from textual.app import App
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, DataTable, Footer, LoadingIndicator, RichLog, Sparkline, Static

from purrge import __version__, awake, tray
from purrge.cleaners import is_admin, run_all, supported_names
from purrge.config import save
from purrge.palette import palettes, theme_order


def fmt_mb(nbytes):
    if nbytes >= 1073741824:
        return f"{nbytes / 1073741824:.2f} gb"
    return f"{nbytes / 1048576:.1f} mb"


def bar(pct, width=20):
    filled = round(pct / 100 * width)
    return "█" * filled + "·" * (width - filled)


class _settingsscreen(ModalScreen):
    BINDINGS = [("escape", "dismiss", "close")]

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg

    def compose(self):
        with Vertical(id="settings"):
            yield Static("[bold]settings[/]", id="settings-title")
            for key in supported_names():
                yield Checkbox(key.replace("_", " "), self.cfg.cleaners.get(key, True), id=f"chk-{key}")
            with Horizontal(id="interval-row"):
                yield Button("-", id="int-down")
                yield Static(f"every {self.cfg.interval_minutes} min", id="int-val")
                yield Button("+", id="int-up")
            yield Button("close", id="settings-close")

    def on_mount(self):
        panel = self.query_one("#settings")
        panel.styles.opacity = 0.0
        panel.styles.animate("opacity", 1.0, duration=0.35)

    def on_checkbox_changed(self, event):
        key = event.checkbox.id.removeprefix("chk-")
        self.cfg.cleaners[key] = bool(event.value)
        save(self.cfg)

    def on_button_pressed(self, event):
        if event.button.id == "settings-close":
            self.dismiss(True)
            return
        step = 5 if event.button.id == "int-up" else -5
        self.cfg.interval_minutes = max(5, min(240, self.cfg.interval_minutes + step))
        save(self.cfg)
        self.query_one("#int-val", Static).update(f"every {self.cfg.interval_minutes} min")

    def action_dismiss(self):
        self.dismiss(True)


class purrgeapp(App):
    TITLE = "purrge"
    CSS = """
    Screen { background: $cat-base; color: $cat-text; }
    #header { height: 3; padding: 1 2; background: $cat-mantle; }
    #status { height: 3; padding: 1 2; background: $cat-surface0; }
    #main { height: 14; }
    #gauges { width: 44; padding: 1 2; border: round $cat-surface1; border-title-color: $cat-mauve; }
    #gauges Static { height: 1; }
    Sparkline { height: 2; margin-bottom: 1; }
    Sparkline > .sparkline--max-color { color: $cat-mauve; }
    Sparkline > .sparkline--min-color { color: $cat-surface1; }
    #spark-cpu > .sparkline--max-color { color: $cat-peach; }
    #table-wrap { padding: 0 1; border: round $cat-surface1; border-title-color: $cat-mauve; }
    DataTable { background: $cat-base; }
    DataTable > .datatable--header { background: $cat-base; color: $cat-subtext0; }
    #busy { height: 1; display: none; color: $cat-mauve; }
    #buttons { height: 3; padding: 0 1; background: $cat-mantle; align: center middle; }
    #buttons Button { min-width: 13; margin: 0 1; background: $cat-surface0; color: $cat-text; border: none; }
    #buttons Button:hover { background: $cat-surface1; color: $cat-mauve; }
    #log { border: round $cat-surface1; background: $cat-mantle; padding: 0 1; border-title-color: $cat-mauve; }
    Footer { background: $cat-mantle; }
    #settings { width: 44; padding: 1 2; background: $cat-mantle; border: round $cat-mauve; color: $cat-text; }
    #settings-title { padding: 0 0 1 0; color: $cat-mauve; }
    #settings Checkbox { background: $cat-mantle; }
    #interval-row { height: 3; align: center middle; }
    #interval-row Button { min-width: 5; background: $cat-surface0; border: none; }
    #int-val { width: 18; text-align: center; padding: 1 0; color: $cat-lavender; }
    #settings-close { margin-top: 1; width: 100%; background: $cat-surface0; border: none; color: $cat-mauve; }
    ModalScreen { align: center middle; }
    Toast { background: $cat-surface0; }
    """
    BINDINGS = [
        ("c", "clean_now", "clean"),
        ("a", "toggle_awake", "awake"),
        ("s", "settings", "settings"),
        ("t", "theme", "theme"),
        ("h", "hide", "tray"),
        ("+", "interval_up", "+5m"),
        ("-", "interval_down", "-5m"),
        ("q", "quit", "quit"),
    ]

    def __init__(self, cfg):
        self.cfg = cfg
        super().__init__()
        self.started = time.monotonic()
        self.session_freed = 0
        self.next_clean = time.monotonic() + cfg.interval_minutes * 60
        self.cleaning = False
        self.last_results = {}
        self.cpu_hist = deque([0.0] * 60, maxlen=60)
        self.ram_hist = deque([0.0] * 60, maxlen=60)

    @property
    def pal(self):
        return palettes[self.cfg.theme]

    def get_css_variables(self):
        variables = super().get_css_variables()
        variables.update({f"cat-{key}": value for key, value in self.pal.items()})
        return variables

    def compose(self):
        yield Static(id="header")
        yield Static(id="status")
        with Horizontal(id="main"):
            with Vertical(id="gauges"):
                yield Static(id="cpu-label")
                yield Sparkline([0.0], summary_function=max, id="spark-cpu")
                yield Static(id="ram-label")
                yield Sparkline([0.0], summary_function=max, id="spark-ram")
                yield Static(id="disk-line")
            with Vertical(id="table-wrap"):
                yield DataTable(id="table", cursor_type="none")
                yield LoadingIndicator(id="busy")
        with Horizontal(id="buttons"):
            yield Button("🧹 clean now", id="btn-clean")
            yield Button("☕ awake", id="btn-awake")
            yield Button("⚙ settings", id="btn-settings")
            yield Button("🎨 theme", id="btn-theme")
            if sys.platform == "win32":
                yield Button("😼 tray", id="btn-hide")
        yield RichLog(id="log", markup=True, wrap=True)
        yield Footer()

    def on_mount(self):
        awake.enable()
        self.query_one("#gauges", Vertical).border_title = "system"
        self.query_one("#table-wrap", Vertical).border_title = "cleaners"
        self.query_one("#log", RichLog).border_title = "activity"
        table = self.query_one("#table", DataTable)
        table.add_columns("cleaner", "last freed", "items", "state")
        self.refresh_table()
        self.set_interval(1.0, self.tick)
        self.logline(f"[{self.pal['mauve']}]purrge v{__version__}[/] started, keep-awake on")
        if sys.platform == "win32" and not is_admin():
            self.logline(f"[{self.pal['peach']}]not running as admin: ram standby + windows update cleans will be skipped[/]")
        self.tick()
        self.run_worker(self.check_update, thread=True)

    def refresh_table(self):
        p = self.pal
        table = self.query_one("#table", DataTable)
        table.clear()
        for key in supported_names():
            r = self.last_results.get(key)
            if not self.cfg.cleaners.get(key, True):
                state, freed, items = f"[{p['overlay0']}]off[/]", "-", "-"
            elif r is None:
                state, freed, items = f"[{p['subtext0']}]waiting[/]", "-", "-"
            elif r.errors:
                state, freed, items = f"[{p['red']}]failed[/]", "-", "-"
            elif r.skipped and not r.items:
                state, freed, items = f"[{p['peach']}]skipped[/]", "-", "-"
            else:
                state, freed, items = f"[{p['green']}]ok[/]", fmt_mb(r.freed_bytes), str(r.items)
            table.add_row(key.replace("_", " "), freed, items, state)

    def tick(self):
        p = self.pal
        up = int(time.monotonic() - self.started)
        hours, rem = divmod(up, 3600)
        minutes, seconds = divmod(rem, 60)
        remain = max(0, int(self.next_clean - time.monotonic()))
        rmin, rsec = divmod(remain, 60)
        badge = f"[{p['green']}]● on[/]" if awake.is_active() else f"[{p['red']}]● off[/]"
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage("c:\\" if sys.platform == "win32" else "/")
        self.cpu_hist.append(cpu)
        self.ram_hist.append(ram)
        self.query_one("#spark-cpu", Sparkline).data = list(self.cpu_hist)
        self.query_one("#spark-ram", Sparkline).data = list(self.ram_hist)
        self.query_one("#header", Static).update(
            f"[bold {p['mauve']}]😼 purrge[/] [{p['overlay0']}]v{__version__}[/]   "
            f"[{p['subtext0']}]uptime[/] [{p['lavender']}]{hours:02}:{minutes:02}:{seconds:02}[/]   "
            f"[{p['subtext0']}]all-time freed[/] [{p['mauve']}]{fmt_mb(self.cfg.total_freed_bytes)}[/]   "
            f"[{p['subtext0']}]theme[/] [{p['lavender']}]{self.cfg.theme}[/]"
        )
        self.query_one("#status", Static).update(
            f"keep-awake {badge}   [{p['subtext0']}]next clean[/] [{p['lavender']}]{rmin:02}:{rsec:02}[/]   "
            f"[{p['subtext0']}]interval[/] [{p['lavender']}]{self.cfg.interval_minutes}m[/]   "
            f"[{p['subtext0']}]session freed[/] [{p['green']}]{fmt_mb(self.session_freed)}[/]"
        )
        self.query_one("#cpu-label", Static).update(f"[{p['subtext0']}]cpu[/] [{p['peach']}]{cpu:.0f}%[/]")
        self.query_one("#ram-label", Static).update(f"[{p['subtext0']}]ram[/] [{p['mauve']}]{ram:.0f}%[/]")
        self.query_one("#disk-line", Static).update(
            f"[{p['subtext0']}]disk[/] [{p['green']}]{bar(disk.percent)}[/] {disk.percent:.0f}%  [{p['overlay0']}]{fmt_mb(disk.free)} free[/]"
        )
        if remain == 0 and not self.cleaning:
            self.action_clean_now()

    def logline(self, message):
        self.query_one("#log", RichLog).write(f"[{self.pal['overlay0']}]{time.strftime('%H:%M:%S')}[/] {message}")

    def check_update(self):
        try:
            with urllib.request.urlopen("https://api.github.com/repos/ege0x77czz/purrge/releases/latest", timeout=5) as r:
                latest = json.load(r)["tag_name"].lstrip("v")
        except Exception:
            return
        if tuple(latest.split(".")) > tuple(__version__.split(".")):
            self.call_from_thread(self.announce_update, latest)

    def announce_update(self, latest):
        self.logline(f"[{self.pal['peach']}]v{latest} is out — github.com/ege0x77czz/purrge/releases[/]")
        self.notify(f"v{latest} is available", title="😼 update", severity="warning")

    def on_button_pressed(self, event):
        actions = {
            "btn-clean": self.action_clean_now,
            "btn-awake": self.action_toggle_awake,
            "btn-settings": self.action_settings,
            "btn-theme": self.action_theme,
            "btn-hide": self.action_hide,
        }
        action = actions.get(event.button.id)
        if action:
            action()

    def action_clean_now(self):
        if self.cleaning:
            return
        self.cleaning = True
        self.query_one("#busy", LoadingIndicator).styles.display = "block"
        self.logline(f"[{self.pal['peach']}]cleaning...[/]")
        self.run_worker(self.do_clean, thread=True)

    def do_clean(self):
        results = run_all(self.cfg)
        self.call_from_thread(self.finish_clean, results)

    def finish_clean(self, results):
        p = self.pal
        freed = 0
        for r in results:
            freed += r.freed_bytes
            self.last_results[r.name] = r
            if r.errors:
                self.logline(f"[{p['red']}]{r.name}: failed[/]")
            elif r.freed_bytes or r.items:
                self.logline(f"[{p['green']}]{r.name}:[/] freed {fmt_mb(r.freed_bytes)}, {r.items} items")
        self.session_freed += freed
        self.cfg.total_freed_bytes += freed
        save(self.cfg)
        self.refresh_table()
        self.next_clean = time.monotonic() + self.cfg.interval_minutes * 60
        self.cleaning = False
        self.query_one("#busy", LoadingIndicator).styles.display = "none"
        self.logline(f"[{p['green']}]clean done,[/] [{p['mauve']}]{fmt_mb(freed)}[/] [{p['green']}]freed[/]")
        self.notify(f"{fmt_mb(freed)} freed", title="😼 clean done")

    def action_toggle_awake(self):
        if awake.is_active():
            awake.disable()
            self.logline(f"[{self.pal['red']}]keep-awake off[/]")
        else:
            awake.enable()
            self.logline(f"[{self.pal['green']}]keep-awake on[/]")

    def action_theme(self):
        current = theme_order.index(self.cfg.theme)
        self.cfg.theme = theme_order[(current + 1) % len(theme_order)]
        save(self.cfg)
        self.refresh_css()
        self.refresh_table()
        self.tick()
        self.logline(f"theme: [{self.pal['mauve']}]{self.cfg.theme}[/]")

    def action_settings(self):
        def closed(_):
            self.next_clean = min(self.next_clean, time.monotonic() + self.cfg.interval_minutes * 60)
            self.refresh_table()
            self.logline("settings saved")

        self.push_screen(_settingsscreen(self.cfg), closed)

    def action_hide(self):
        if sys.platform != "win32":
            self.logline(f"[{self.pal['peach']}]tray mode is windows-only for now[/]")
            return
        tray.start(
            lambda: self.call_from_thread(self.show_from_tray),
            lambda: self.call_from_thread(self.action_clean_now),
            lambda: self.call_from_thread(self.exit),
        )
        tray.hide_console()
        self.logline(f"[{self.pal['lavender']}]hidden to tray, click the cat to come back[/]")

    def show_from_tray(self):
        tray.show_console()
        self.logline(f"[{self.pal['lavender']}]back from tray[/]")

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
        self.logline(f"interval set to [{self.pal['lavender']}]{minutes}m[/]")
