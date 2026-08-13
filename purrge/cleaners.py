import os
import time
from dataclasses import dataclass
from pathlib import Path


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
