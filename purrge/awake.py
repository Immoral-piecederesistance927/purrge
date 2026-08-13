import ctypes

es_continuous = 0x80000000
es_system_required = 0x00000001
es_display_required = 0x00000002

_active = False


def enable():
    global _active
    ctypes.windll.kernel32.SetThreadExecutionState(es_continuous | es_system_required | es_display_required)
    _active = True


def disable():
    global _active
    ctypes.windll.kernel32.SetThreadExecutionState(es_continuous)
    _active = False


def is_active():
    return _active
