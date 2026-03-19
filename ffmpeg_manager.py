"""
ffmpeg_manager.py
Detects FFmpeg, and on Windows offers to auto-download a static build.
"""

import os
import sys
import platform
import subprocess
import zipfile
import threading
import urllib.request
import shutil

# Where we'll install FFmpeg if not on PATH
_LOCAL_DIR  = os.path.join(os.path.dirname(__file__), "ffmpeg_bin")
_LOCAL_EXE  = os.path.join(_LOCAL_DIR, "ffmpeg.exe")

# GitHub-hosted minimal FFmpeg Windows build (shared by BtbN releases)
_WIN_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/"
    "latest/ffmpeg-master-latest-win64-gpl.zip"
)


def is_available() -> bool:
    """Return True if ffmpeg is callable (PATH or local bin)."""
    if _local_on_path():
        return True
    return _which("ffmpeg") is not None


def ensure_on_path():
    """Add our local ffmpeg_bin to PATH for this process if present."""
    if os.path.isfile(_LOCAL_EXE):
        os.environ["PATH"] = _LOCAL_DIR + os.pathsep + os.environ.get("PATH", "")


def get_version() -> str:
    try:
        out = subprocess.check_output(
            ["ffmpeg", "-version"],
            stderr=subprocess.STDOUT, text=True)
        return out.splitlines()[0].replace("ffmpeg version ", "").split(" ")[0]
    except Exception:
        return "not found"


def download_ffmpeg(progress_cb=None, done_cb=None):
    """
    Download FFmpeg on Windows in a background thread.
    progress_cb(fraction)  — 0.0 to 1.0
    done_cb(success, msg)
    """
    if platform.system() != "Windows":
        if done_cb:
            done_cb(False,
                    "Auto-install only supported on Windows.\n"
                    "Please install FFmpeg manually:\n"
                    "https://ffmpeg.org/download.html")
        return

    def _run():
        try:
            os.makedirs(_LOCAL_DIR, exist_ok=True)
            zip_path = os.path.join(_LOCAL_DIR, "ffmpeg.zip")

            # ── Download ──────────────────────────────────────────────────────
            def _reporthook(count, block, total):
                if total > 0 and progress_cb:
                    progress_cb(min(1.0, count * block / total * 0.8))

            urllib.request.urlretrieve(_WIN_URL, zip_path, _reporthook)

            if progress_cb:
                progress_cb(0.85)

            # ── Extract only ffmpeg.exe / ffprobe.exe ─────────────────────────
            with zipfile.ZipFile(zip_path, "r") as z:
                for member in z.namelist():
                    fname = os.path.basename(member)
                    if fname in ("ffmpeg.exe", "ffprobe.exe") and fname:
                        with z.open(member) as src, \
                                open(os.path.join(_LOCAL_DIR, fname),
                                     "wb") as dst:
                            shutil.copyfileobj(src, dst)

            os.remove(zip_path)

            if progress_cb:
                progress_cb(1.0)

            ensure_on_path()

            if done_cb:
                done_cb(True, f"FFmpeg installed to:\n{_LOCAL_DIR}")

        except Exception as e:
            if done_cb:
                done_cb(False, f"Download failed:\n{e}\n\n"
                        "Install manually from https://ffmpeg.org/download.html")

    threading.Thread(target=_run, daemon=True).start()


# ── helpers ───────────────────────────────────────────────────────────────────

def _which(cmd):
    return shutil.which(cmd)


def _local_on_path():
    return os.path.isfile(_LOCAL_EXE)