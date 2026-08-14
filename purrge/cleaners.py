import ctypes
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import psutil

from purrge.config import default_cleaners

win_only = {"thumbnails", "shader_cache", "windows_update", "ram_standby"}


def supported_names():
    if sys.platform == "win32":
        return list(default_cleaners)
    return [name for name in default_cleaners if name not in win_only]


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
    if sys.platform != "win32":
        return [Path(tempfile.gettempdir())]
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
    if sys.platform == "darwin":
        caches = Path.home() / "Library" / "Caches"
        return [
            browserspec("chrome", "google chrome", caches / "Google" / "Chrome", ["*"]),
            browserspec("edge", "microsoft edge", caches / "Microsoft Edge", ["*"]),
            browserspec("firefox", "firefox", caches / "Firefox" / "Profiles", ["*/cache2"]),
        ]
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


def default_discord_specs():
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "discord"
        return [browserspec("discord", "discord", root, ["Cache", "Code Cache", "GPUCache"])]
    roaming = Path(os.environ.get("APPDATA", "."))
    return [browserspec("discord", "discord.exe", roaming / "discord", ["cache", "code cache", "gpucache"])]


class discordcleaner(browsercachecleaner):
    name = "discord"

    def __init__(self, specs=None, running=None):
        super().__init__(specs if specs is not None else default_discord_specs(), running)


def default_thumb_root():
    return Path(os.environ.get("LOCALAPPDATA", ".")) / "microsoft" / "windows" / "explorer"


class thumbcleaner:
    name = "thumbnails"

    def __init__(self, root=None):
        self.root = root if root is not None else default_thumb_root()

    def clean(self):
        result = cleanresult(self.name)
        if not self.root.exists():
            return result
        for p in list(self.root.glob("thumbcache_*.db")) + list(self.root.glob("iconcache_*.db")):
            try:
                size = p.stat().st_size
                p.unlink()
                result.freed_bytes += size
                result.items += 1
            except OSError:
                result.skipped += 1
        return result


def default_shader_roots():
    local = Path(os.environ.get("LOCALAPPDATA", "."))
    return [local / "d3dscache", local / "nvidia" / "dxcache", local / "nvidia" / "glcache"]


class shadercleaner(tempcleaner):
    name = "shader_cache"

    def __init__(self, roots=None):
        super().__init__(roots if roots is not None else default_shader_roots())


def default_wer_roots():
    if sys.platform == "darwin":
        return [Path.home() / "Library" / "Logs" / "DiagnosticReports"]
    local = Path(os.environ.get("LOCALAPPDATA", ".")) / "microsoft" / "windows" / "wer"
    progdata = Path(os.environ.get("PROGRAMDATA", r"c:\programdata")) / "microsoft" / "windows" / "wer"
    return [local / "reportqueue", local / "reportarchive", progdata / "reportqueue", progdata / "reportarchive"]


class wercleaner(tempcleaner):
    name = "crash_dumps"

    def __init__(self, roots=None):
        super().__init__(roots if roots is not None else default_wer_roots())


def default_wu_roots():
    return [Path(os.environ.get("SYSTEMROOT", r"c:\windows")) / "softwaredistribution" / "download"]


class wucleaner(tempcleaner):
    name = "windows_update"

    def __init__(self, roots=None):
        super().__init__(roots if roots is not None else default_wu_roots())

    def clean(self):
        if not is_admin():
            return cleanresult(self.name, skipped=1)
        return super().clean()


def is_admin():
    if sys.platform != "win32":
        return os.geteuid() == 0
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
    process = ctypes.c_void_p(-1)
    if not advapi.OpenProcessToken(process, 0x28, ctypes.byref(token)):
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


def dns_command():
    if sys.platform == "darwin":
        return ["dscacheutil", "-flushcache"]
    return ["ipconfig", "/flushdns"]


class dnscleaner:
    name = "dns"

    def clean(self):
        result = cleanresult(self.name)
        flags = 0x08000000 if sys.platform == "win32" else 0
        try:
            subprocess.run(dns_command(), capture_output=True, check=True, creationflags=flags)
            result.items = 1
        except (OSError, subprocess.CalledProcessError):
            result.errors = 1
        return result


def all_cleaners():
    instances = {
        "temp": tempcleaner,
        "browser_cache": browsercachecleaner,
        "discord": discordcleaner,
        "thumbnails": thumbcleaner,
        "crash_dumps": wercleaner,
        "shader_cache": shadercleaner,
        "windows_update": wucleaner,
        "ram_standby": ramstandbycleaner,
        "dns": dnscleaner,
    }
    return [instances[name]() for name in supported_names()]


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
