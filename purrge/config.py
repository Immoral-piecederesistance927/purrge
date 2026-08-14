import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from purrge.palette import palettes

default_cleaners = {
    "temp": True,
    "browser_cache": True,
    "discord": True,
    "thumbnails": True,
    "crash_dumps": True,
    "shader_cache": True,
    "windows_update": True,
    "ram_standby": True,
    "dns": True,
}


@dataclass
class config:
    interval_minutes: int = 30
    cleaners: dict = field(default_factory=lambda: dict(default_cleaners))
    total_freed_bytes: int = 0
    theme: str = "mocha"


def config_path():
    return Path(os.environ["APPDATA"]) / "purrge" / "config.json"


def load(path=None):
    path = path or config_path()
    try:
        raw = json.loads(path.read_text())
        cleaners = dict(default_cleaners)
        for key, value in raw.get("cleaners", {}).items():
            if key in default_cleaners:
                cleaners[key] = bool(value)
        cfg = config(
            int(raw.get("interval_minutes", 30)),
            cleaners,
            max(0, int(raw.get("total_freed_bytes", 0))),
            str(raw.get("theme", "mocha")),
        )
    except (OSError, ValueError):
        cfg = config()
    cfg.interval_minutes = max(5, min(240, cfg.interval_minutes))
    if cfg.theme not in palettes:
        cfg.theme = "mocha"
    save(cfg, path)
    return cfg


def save(cfg, path=None):
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "interval_minutes": cfg.interval_minutes,
                "cleaners": cfg.cleaners,
                "total_freed_bytes": cfg.total_freed_bytes,
                "theme": cfg.theme,
            },
            indent=2,
        )
    )
