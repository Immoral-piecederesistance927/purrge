import time

import psutil
from textual.app import App
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, DataTable, Footer, RichLog, Static

from purrge import __version__, awake, tray
from purrge.cleaners import is_admin, run_all
from purrge.config import default_cleaners, save


def fmt_mb(nbytes):
    if nbytes >= 1073741824:
        return f"{nbytes / 1073741824:.2f} gb"
    return f"{nbytes / 1048576:.1f} mb"


def bar(pct, width=22):
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def gauge_color(pct):
    if pct < 60:
        return "#a6e3a1"
    if pct < 85:
        return "#fab387"
    return "#f38ba8"


class _settingsscreen(ModalScreen):
    BINDINGS = [("escape", "dismiss", "close")]

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg

    def compose(self):
        with Vertical(id="settings"):
            yield Static("[bold #cba6f7]settings[/]", id="settings-title")
            for key in default_cleaners:
                yield Checkbox(key.replace("_", " "), self.cfg.cleaners.get(key, True), id=f"chk-{key}")
            with Horizontal(id="interval-row"):
                yield Button("-", id="int-down")
                yield Static(f"every {self.cfg.interval_minutes} min", id="int-val")
                yield Button("+", id="int-up")
            yield Button("close", id="settings-close")

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
    Screen { background: #1e1e2e; color: #cdd6f4; }
    #header { height: 3; padding: 1 2; background: #181825; }
    #status { height: 3; padding: 1 2; background: #313244; }
    #main { height: 13; }
    #gauges { width: 42; padding: 1 2; border: round #45475a; border-title-color: #cba6f7; }
    #table-wrap { padding: 0 1; border: round #45475a; border-title-color: #cba6f7; }
    DataTable { background: #1e1e2e; }
    DataTable > .datatable--header { background: #1e1e2e; color: #a6adc8; }
    DataTable > .datatable--cursor { background: #313244; }
    #buttons { height: 3; padding: 0 1; background: #181825; align: center middle; }
    #buttons Button { min-width: 14; margin: 0 1; background: #313244; color: #cdd6f4; border: none; }
    #buttons Button:hover { background: #45475a; color: #cba6f7; }
    #log { border: round #45475a; background: #181825; padding: 0 1; border-title-color: #cba6f7; }
    Footer { background: #181825; }
    #settings { width: 44; padding: 1 2; background: #181825; border: round #cba6f7; }
    #settings-title { padding: 0 0 1 0; }
    #settings Checkbox { background: #181825; }
    #interval-row { height: 3; align: center middle; }
    #interval-row Button { min-width: 5; background: #313244; border: none; }
    #int-val { width: 18; text-align: center; padding: 1 0; color: #b4befe; }
    #settings-close { margin-top: 1; width: 100%; background: #313244; border: none; color: #cba6f7; }
    ModalScreen { align: center middle; }
    """
    BINDINGS = [
        ("c", "clean_now", "clean"),
        ("a", "toggle_awake", "awake"),
        ("s", "settings", "settings"),
        ("h", "hide", "tray"),
        ("+", "interval_up", "+5m"),
        ("-", "interval_down", "-5m"),
        ("q", "quit", "quit"),
    ]

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.started = time.monotonic()
        self.session_freed = 0
        self.next_clean = time.monotonic() + cfg.interval_minutes * 60
        self.cleaning = False
        self.last_results = {}

    def compose(self):
        yield Static(id="header")
        yield Static(id="status")
        with Horizontal(id="main"):
            yield Static(id="gauges")
            with Vertical(id="table-wrap"):
                yield DataTable(id="table", cursor_type="none")
        with Horizontal(id="buttons"):
            yield Button("🧹 clean now", id="btn-clean")
            yield Button("☕ awake", id="btn-awake")
            yield Button("⚙ settings", id="btn-settings")
            yield Button("😼 tray", id="btn-hide")
        yield RichLog(id="log", markup=True, wrap=True)
        yield Footer()

    def on_mount(self):
        awake.enable()
        self.query_one("#gauges", Static).border_title = "system"
        self.query_one("#table-wrap", Vertical).border_title = "cleaners"
        self.query_one("#log", RichLog).border_title = "activity"
        table = self.query_one("#table", DataTable)
        table.add_columns("cleaner", "last freed", "items", "state")
        self.refresh_table()
        self.set_interval(1.0, self.tick)
        self.logline(f"[#cba6f7]purrge v{__version__}[/] started, keep-awake on")
        if not is_admin():
            self.logline("[#fab387]not running as admin: ram standby + windows update cleans will be skipped[/]")
        self.tick()

    def refresh_table(self):
        table = self.query_one("#table", DataTable)
        table.clear()
        for key in default_cleaners:
            r = self.last_results.get(key)
            if not self.cfg.cleaners.get(key, True):
                state, freed, items = "[#6c7086]off[/]", "-", "-"
            elif r is None:
                state, freed, items = "[#a6adc8]waiting[/]", "-", "-"
            elif r.errors:
                state, freed, items = "[#f38ba8]failed[/]", "-", "-"
            elif r.skipped and not r.items:
                state, freed, items = "[#fab387]skipped[/]", "-", "-"
            else:
                state, freed, items = "[#a6e3a1]ok[/]", fmt_mb(r.freed_bytes), str(r.items)
            table.add_row(key.replace("_", " "), freed, items, state)

    def tick(self):
        up = int(time.monotonic() - self.started)
        hours, rem = divmod(up, 3600)
        minutes, seconds = divmod(rem, 60)
        remain = max(0, int(self.next_clean - time.monotonic()))
        rmin, rsec = divmod(remain, 60)
        badge = "[#a6e3a1]● on[/]" if awake.is_active() else "[#f38ba8]● off[/]"
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage("c:\\")
        self.query_one("#header", Static).update(
            f"[bold #cba6f7]😼 purrge[/] [#6c7086]v{__version__}[/]   "
            f"[#a6adc8]uptime[/] [#b4befe]{hours:02}:{minutes:02}:{seconds:02}[/]   "
            f"[#a6adc8]all-time freed[/] [#cba6f7]{fmt_mb(self.cfg.total_freed_bytes)}[/]"
        )
        self.query_one("#status", Static).update(
            f"keep-awake {badge}   [#a6adc8]next clean[/] [#b4befe]{rmin:02}:{rsec:02}[/]   "
            f"[#a6adc8]interval[/] [#b4befe]{self.cfg.interval_minutes}m[/]   "
            f"[#a6adc8]session freed[/] [#a6e3a1]{fmt_mb(self.session_freed)}[/]"
        )
        self.query_one("#gauges", Static).update(
            f"[#a6adc8]cpu [/] [{gauge_color(cpu)}]{bar(cpu)}[/] {cpu:4.0f}%\n"
            f"[#a6adc8]ram [/] [{gauge_color(ram)}]{bar(ram)}[/] {ram:4.0f}%\n"
            f"[#a6adc8]disk[/] [{gauge_color(disk.percent)}]{bar(disk.percent)}[/] {disk.percent:4.0f}%  [#6c7086]{fmt_mb(disk.free)} free[/]"
        )
        if remain == 0 and not self.cleaning:
            self.action_clean_now()

    def logline(self, message):
        self.query_one("#log", RichLog).write(f"[#6c7086]{time.strftime('%H:%M:%S')}[/] {message}")

    def on_button_pressed(self, event):
        actions = {
            "btn-clean": self.action_clean_now,
            "btn-awake": self.action_toggle_awake,
            "btn-settings": self.action_settings,
            "btn-hide": self.action_hide,
        }
        action = actions.get(event.button.id)
        if action:
            action()

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
        freed = 0
        for r in results:
            freed += r.freed_bytes
            self.last_results[r.name] = r
            if r.errors:
                self.logline(f"[#f38ba8]{r.name}: failed[/]")
            elif r.freed_bytes or r.items:
                self.logline(f"[#a6e3a1]{r.name}:[/] freed {fmt_mb(r.freed_bytes)}, {r.items} items")
        self.session_freed += freed
        self.cfg.total_freed_bytes += freed
        save(self.cfg)
        self.refresh_table()
        self.next_clean = time.monotonic() + self.cfg.interval_minutes * 60
        self.cleaning = False
        self.logline(f"[#a6e3a1]clean done,[/] [#cba6f7]{fmt_mb(freed)}[/] [#a6e3a1]freed[/]")

    def action_toggle_awake(self):
        if awake.is_active():
            awake.disable()
            self.logline("[#f38ba8]keep-awake off[/]")
        else:
            awake.enable()
            self.logline("[#a6e3a1]keep-awake on[/]")

    def action_settings(self):
        def closed(_):
            self.next_clean = min(self.next_clean, time.monotonic() + self.cfg.interval_minutes * 60)
            self.refresh_table()
            self.logline("settings saved")

        self.push_screen(_settingsscreen(self.cfg), closed)

    def action_hide(self):
        tray.start(
            lambda: self.call_from_thread(self.show_from_tray),
            lambda: self.call_from_thread(self.action_clean_now),
            lambda: self.call_from_thread(self.exit),
        )
        tray.hide_console()
        self.logline("[#b4befe]hidden to tray, click the cat to come back[/]")

    def show_from_tray(self):
        tray.show_console()
        self.logline("[#b4befe]back from tray[/]")

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
