import os
import time
from dataclasses import dataclass
from pathlib import Path

import psutil


@dataclass
class cleanresult:
    name: str
    freed_bytes: int = 0
    items: int = 0
    skipped: int = 0
    errors: int = 0


def sweep(root, min_age_seconds=0):
    result = cleanresult("sweep")
    root = Path(root)
    if not root.exists():
        return result
    cutoff = time.time() - min_age_seconds
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        if "_mei" in dirpath.lower():
            continue
        for fn in filenames:
            p = Path(dirpath) / fn
            try:
                st = p.stat()
                if st.st_mtime <= cutoff:
                    p.unlink()
                    result.freed_bytes += st.st_size
                    result.items += 1
                else:
                    result.skipped += 1
            except OSError:
                result.skipped += 1
        for dn in dirnames:
            if "_mei" in dn.lower():
                continue
            try:
                (Path(dirpath) / dn).rmdir()
            except OSError:
                pass
    return result


def default_temp_roots():
    roots = []
    tmp = os.environ.get("TEMP")
    if tmp:
        roots.append(Path(tmp))
    windir = os.environ.get("SYSTEMROOT", r"c:\windows")
    roots.append(Path(windir) / "temp")
    return roots


class tempcleaner:
    name = "temp"

    def __init__(self, roots=None, min_age_seconds=3600):
        self.roots = roots if roots is not None else default_temp_roots()
        self.min_age_seconds = min_age_seconds

    def clean(self):
        result = cleanresult(self.name)
        for root in self.roots:
            r = sweep(root, self.min_age_seconds)
            result.freed_bytes += r.freed_bytes
            result.items += r.items
            result.skipped += r.skipped
        return result


@dataclass
class browserspec:
    name: str
    process: str
    root: Path
    patterns: list


def default_browser_specs():
    local = Path(os.environ.get("LOCALAPPDATA", "."))
    return [
        browserspec("chrome", "chrome.exe", local / "google" / "chrome" / "user data", ["*/cache", "*/code cache"]),
        browserspec("edge", "msedge.exe", local / "microsoft" / "edge" / "user data", ["*/cache", "*/code cache"]),
        browserspec("firefox", "firefox.exe", local / "mozilla" / "firefox" / "profiles", ["*/cache2"]),
    ]


def process_running(name):
    name = name.lower()
    for p in psutil.process_iter(["name"]):
        if (p.info["name"] or "").lower() == name:
            return True
    return False


class browsercachecleaner:
    name = "browser_cache"

    def __init__(self, specs=None, running=None):
        self.specs = specs if specs is not None else default_browser_specs()
        self.running = running or process_running

    def clean(self):
        result = cleanresult(self.name)
        for spec in self.specs:
            if self.running(spec.process):
                result.skipped += 1
                continue
            for pattern in spec.patterns:
                for cache_dir in spec.root.glob(pattern):
                    r = sweep(cache_dir)
                    result.freed_bytes += r.freed_bytes
                    result.items += r.items
                    result.skipped += r.skipped
        return result
