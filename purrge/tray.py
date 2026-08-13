import ctypes
import threading

_icon = None


def console_window():
    return ctypes.windll.kernel32.GetConsoleWindow()


def hide_console():
    hwnd = console_window()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 0)


def show_console():
    hwnd = console_window()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 5)
        ctypes.windll.user32.SetForegroundWindow(hwnd)


def make_image():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (30, 30, 46, 255))
    draw = ImageDraw.Draw(img)
    draw.polygon([(14, 30), (17, 8), (30, 22)], fill=(203, 166, 247, 255))
    draw.polygon([(50, 30), (47, 8), (34, 22)], fill=(203, 166, 247, 255))
    draw.ellipse((10, 18, 54, 58), fill=(203, 166, 247, 255))
    draw.ellipse((22, 32, 28, 38), fill=(30, 30, 46, 255))
    draw.ellipse((36, 32, 42, 38), fill=(30, 30, 46, 255))
    return img


def start(on_show, on_clean, on_quit):
    global _icon
    if _icon is not None:
        return _icon
    import pystray

    menu = pystray.Menu(
        pystray.MenuItem("show", lambda icon, item: on_show(), default=True),
        pystray.MenuItem("clean now", lambda icon, item: on_clean()),
        pystray.MenuItem("quit", lambda icon, item: on_quit()),
    )
    _icon = pystray.Icon("purrge", make_image(), "purrge", menu)
    threading.Thread(target=_icon.run, daemon=True).start()
    return _icon


def stop():
    global _icon
    if _icon is not None:
        _icon.stop()
        _icon = None
