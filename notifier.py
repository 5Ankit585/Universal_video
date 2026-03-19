"""
notifier.py
Windows 10/11 toast notifications via win10toast (if installed)
or a fallback using the system tray balloon via ctypes.
"""

import platform
import threading


def notify(title: str, message: str, duration: int = 5):
    """
    Show a desktop notification. Non-blocking — runs in background thread.
    Works on Windows 10/11. Silent on other platforms.
    """
    if platform.system() != "Windows":
        return
    threading.Thread(
        target=_show, args=(title, message, duration),
        daemon=True).start()


def _show(title, message, duration):
    # ── Method 1: win10toast (pip install win10toast) ─────────────────────────
    try:
        from win10toast import ToastNotifier
        t = ToastNotifier()
        t.show_toast(title, message,
                     duration=duration,
                     threaded=True)
        return
    except ImportError:
        pass

    # ── Method 2: ctypes balloon tip via Windows Shell ────────────────────────
    try:
        import ctypes
        from ctypes import wintypes

        NIF_MESSAGE  = 0x01
        NIF_ICON     = 0x02
        NIF_TIP      = 0x04
        NIF_INFO     = 0x10
        NIM_ADD      = 0x00
        NIM_MODIFY   = 0x01
        NIM_DELETE   = 0x02
        NIIF_INFO    = 0x01
        WM_USER      = 0x0400

        class NOTIFYICONDATA(ctypes.Structure):
            _fields_ = [
                ("cbSize",           wintypes.DWORD),
                ("hWnd",             wintypes.HWND),
                ("uID",              wintypes.UINT),
                ("uFlags",           wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT),
                ("hIcon",            wintypes.HANDLE),
                ("szTip",            ctypes.c_wchar * 128),
                ("dwState",          wintypes.DWORD),
                ("dwStateMask",      wintypes.DWORD),
                ("szInfo",           ctypes.c_wchar * 256),
                ("uTimeout",         wintypes.UINT),
                ("szInfoTitle",      ctypes.c_wchar * 64),
                ("dwInfoFlags",      wintypes.DWORD),
            ]

        shell32 = ctypes.windll.shell32
        nid = NOTIFYICONDATA()
        nid.cbSize     = ctypes.sizeof(NOTIFYICONDATA)
        nid.uFlags     = NIF_INFO
        nid.szInfo     = message[:255]
        nid.szInfoTitle = title[:63]
        nid.uTimeout   = duration * 1000
        nid.dwInfoFlags = NIIF_INFO

        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        import time
        time.sleep(duration)
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
    except Exception:
        pass   # silently skip on unsupported systems