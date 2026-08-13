# purrge

keeps your pc awake and periodically purges junk. a modern terminal dashboard for windows, dressed in catppuccin mocha.

## what it does

- **keep-awake** — tells windows not to sleep and not to turn off the display while purrge runs, via the official `SetThreadExecutionState` api. no mouse-jiggling hacks. toggle it any time with one key.
- **periodic cleaning** — every 30 minutes by default (adjustable 5–240), purrge runs its cleaners and reports how much it freed:
  - **temp** — `%TEMP%` and `c:\windows\temp`, only files older than one hour, locked files silently skipped
  - **browser cache** — chrome, edge and firefox cache folders, and only while the browser is closed. never touches history, cookies or passwords.
  - **ram standby** — purges the standby memory list so active apps get fresh memory (needs admin)
  - **dns** — flushes the resolver cache
- **live dashboard** — uptime, keep-awake state, countdown to the next clean, total freed, live cpu and ram gauges, scrolling activity log.

## keys

| key | action |
| --- | --- |
| `c` | clean now |
| `a` | toggle keep-awake |
| `+` / `-` | clean interval +5 / -5 minutes |
| `q` | quit |

## download

grab `purrge.exe` from the [latest release](../../releases/latest) and run it. windows will ask for admin once at launch — that is what the ram standby cleaner needs; everything else works without it.

works on windows 10, windows 11 and windows server 2016+.

## run from source

```
pip install -e .
python -m purrge
```

## build

```
pip install -e .[dev]
pyinstaller --onefile --name purrge --uac-admin --collect-submodules textual entry.py
```

## config

`%APPDATA%\purrge\config.json` — clean interval and per-cleaner toggles. edited live from the dashboard, or by hand:

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
