import ctypes
import subprocess
import sys

es_continuous = 0x80000000
es_system_required = 0x00000001
es_display_required = 0x00000002

_active = False
_caffeinate = None


def enable():
    global _active, _caffeinate
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetThreadExecutionState(es_continuous | es_system_required | es_display_required)
    elif _caffeinate is None:
        try:
            _caffeinate = subprocess.Popen(["caffeinate", "-d", "-i"])
        except OSError:
            _caffeinate = None
    _active = True


def disable():
    global _active, _caffeinate
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetThreadExecutionState(es_continuous)
    elif _caffeinate is not None:
        _caffeinate.terminate()
        _caffeinate = None
    _active = False


def is_active():
    return _active
