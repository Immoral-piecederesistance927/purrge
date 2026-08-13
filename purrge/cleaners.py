import ctypes
import os
import subprocess
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


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (OSError, AttributeError):
        return False


class luid(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_int32)]


class luid_and_attributes(ctypes.Structure):
    _fields_ = [("luid", luid), ("attributes", ctypes.c_uint32)]


class token_privileges(ctypes.Structure):
    _fields_ = [("count", ctypes.c_uint32), ("privileges", luid_and_attributes * 1)]


def enable_privilege(name):
    advapi = ctypes.windll.advapi32
    kernel = ctypes.windll.kernel32
    token = ctypes.c_void_p()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x28, ctypes.byref(token)):
        return False
    value = luid()
    if not advapi.LookupPrivilegeValueW(None, name, ctypes.byref(value)):
        kernel.CloseHandle(token)
        return False
    privs = token_privileges(1, (luid_and_attributes * 1)(luid_and_attributes(value, 0x2)))
    ok = advapi.AdjustTokenPrivileges(token, False, ctypes.byref(privs), 0, None, None)
    kernel.CloseHandle(token)
    return bool(ok)


class ramstandbycleaner:
    name = "ram_standby"

    def clean(self):
        result = cleanresult(self.name)
        if not is_admin():
            result.skipped = 1
            return result
        enable_privilege("SeProfileSingleProcessPrivilege")
        before = psutil.virtual_memory().available
        command = ctypes.c_int(4)
        status = ctypes.windll.ntdll.NtSetSystemInformation(80, ctypes.byref(command), ctypes.sizeof(command))
        if status != 0:
            result.errors = 1
            return result
        result.items = 1
        result.freed_bytes = max(0, psutil.virtual_memory().available - before)
        return result


class dnscleaner:
    name = "dns"

    def clean(self):
        result = cleanresult(self.name)
        try:
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True, check=True, creationflags=0x08000000)
            result.items = 1
        except (OSError, subprocess.CalledProcessError):
            result.errors = 1
        return result


def all_cleaners():
    return [tempcleaner(), browsercachecleaner(), ramstandbycleaner(), dnscleaner()]


def run_all(cfg, cleaners=None):
    cleaners = cleaners if cleaners is not None else all_cleaners()
    results = []
    for c in cleaners:
        if not cfg.cleaners.get(c.name, False):
            continue
        try:
            results.append(c.clean())
        except Exception:
            results.append(cleanresult(c.name, errors=1))
    return results
