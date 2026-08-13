# purrge — design spec

date: 2026-08-13
status: approved pending user review

## overview

purrge is a windows cli tool that keeps the machine awake and periodically cleans junk that degrades perceived performance. it runs as a live terminal dashboard themed with the catppuccin mocha palette. it ships as a single `purrge.exe` built with pyinstaller and released on github.

## goals

- keep the system and display awake while running (official windows api, no input-simulation hacks)
- periodically clean: temp files, browser caches, ram standby list, dns cache
- live dashboard: uptime, keep-awake state, countdown to next clean, total mb freed, live cpu/ram gauges, scrolling log
- configurable clean interval, adjustable from the dashboard and persisted
- single-file exe, github release pipeline via github actions
- works on windows 10/11 and windows server 2016+

## non-goals

- no license-expiry shutdown bypass of any kind. an unactivated windows server eval shutting down hourly is a licensing matter; the legitimate fixes are `slmgr /rearm` or proper activation. purrge will never fight forced os shutdowns.
- no shutdown-guard / shutdown-abort feature
- no windows service mode (dashboard in an rdp session is sufficient; disconnect keeps it running)
- no browser history/password/cookie touching — cache directories only
- no recycle bin emptying

## stack

- python 3.11+
- textual — tui framework for the dashboard
- psutil — cpu/ram metrics and browser-process detection
- pyinstaller — onefile exe build with `--uac-admin`
- pytest — tests for cleaner logic

## architecture

five focused modules under `purrge/`:

### awake.py

wraps `SetThreadExecutionState` via ctypes.

- `enable()` → `ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED`
- `disable()` → `ES_CONTINUOUS`
- state is queryable for the ui; toggled with a keybinding

### cleaners.py

one class per cleaner, all implementing a small protocol: `name`, `enabled(config)`, `clean() -> CleanResult(freed_bytes, items, skipped, errors)`.

- **temp cleaner**: `%TEMP%` and `C:\Windows\Temp`. deletes files and empty dirs older than 1 hour; silently skips locked/in-use files. reports bytes freed.
- **browser cache cleaner**: chrome, edge, firefox cache directories under the user profile. runs only when the matching browser process is not running (checked via psutil). cache dirs only — never history, cookies, logins.
- **ram standby cleaner**: purges the standby memory list via `NtSetSystemInformation(SystemMemoryListInformation, MemoryPurgeStandbyList)`. requires admin + `SeProfileSingleProcessPrivilege` (enabled at startup via ctypes). reports standby mb before/after.
- **dns cleaner**: `ipconfig /flushdns` via subprocess, no window flash.

a `run_all(config)` helper runs enabled cleaners in order, aggregates results, and never lets one cleaner's exception break the run.

### config.py

json at `%APPDATA%\purrge\config.json`. schema:

```json
{
  "interval_minutes": 30,
  "cleaners": {
    "temp": true,
    "browser_cache": true,
    "ram_standby": true,
    "dns": true
  }
}
```

- loaded at startup, defaults created if missing or corrupt
- `interval_minutes` clamped to 5–240
- saved immediately when changed from the dashboard

### ui.py

textual app, catppuccin mocha palette throughout (base #1e1e2e, text #cdd6f4, mauve #cba6f7, green #a6e3a1, peach #fab387, red #f38ba8, surface0 #313244, lavender #b4befe).

layout:

- header: purrge logo/title, version, session uptime
- status row: keep-awake state (on/off badge), next clean countdown, total mb freed this session
- gauges: live cpu and ram bars (psutil, 1s refresh)
- log panel: timestamped scrolling log of clean runs and state changes

keybindings:

- `c` — clean now
- `a` — toggle keep-awake
- `+` / `-` — clean interval up/down (persisted)
- `q` — quit (restores execution state)

### app.py / \_\_main\_\_.py

entry point: parses no-frills args (`--version`), checks admin (warns in-ui if ram standby cleaner is enabled without admin), starts the textual app, schedules the periodic clean with textual timers.

## error handling

- every cleaner catches and logs its own exceptions; a failing cleaner never stops the loop or crashes the ui
- locked files are expected on windows: skip and count, don't warn-spam
- config corruption → regenerate defaults, log one line
- on quit, execution state is always restored (`ES_CONTINUOUS`), including on ctrl+c

## build and release

- pyinstaller: `--onefile --name purrge --uac-admin` (console app; uac prompt on launch because of the ram standby cleaner)
- github repo `ege0x77czz/purrge`, **private initially**, made public later
- github actions workflow: on push of tag `v*`, windows-latest runner builds the exe and creates a github release with `purrge.exe` attached
- readme: english, lowercase style, catppuccin mocha screenshot, feature list, download link to latest release

## testing

- pytest for cleaner logic against tmp_path fixtures: age filtering, size accounting, locked-file skipping (simulated via open handles), config load/clamp/save round-trips
- awake/ram/dns are thin os wrappers: verified manually on windows 10 and windows server
- dashboard verified manually (textual snapshot testing skipped — yagni for v1)

## conventions

- code entirely lowercase english, zero comments
- commits by `ege0x77czz <egesha.de@gmail.com>`, no co-authored-by trailer
