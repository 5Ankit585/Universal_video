"""
compressor.py  —  Compress videos using FFmpeg (H.265 / CRF)
H.265 typically gives 40-60% smaller files vs the original H.264 download.
"""

import os
import subprocess
import threading


# ── Preset definitions ────────────────────────────────────────────────────────
# crf: lower = better quality / bigger file  (18=great, 28=small, 23=balanced)
PRESETS = {
    "Maximum Compression":  {"crf": 30, "preset": "slow",   "label": "~60% smaller"},
    "Balanced (Recommended)": {"crf": 24, "preset": "medium", "label": "~45% smaller"},
    "High Quality":          {"crf": 20, "preset": "medium", "label": "~25% smaller"},
    "Lossless":              {"crf": 18, "preset": "fast",   "label": "~10% smaller"},
}


def get_preset_names():
    return list(PRESETS.keys())


def get_preset_label(name):
    return PRESETS.get(name, {}).get("label", "")


def compress_video(
    input_path: str,
    output_path: str,
    preset_name: str = "Balanced (Recommended)",
    progress_callback=None,   # fn(fraction 0.0–1.0)
    status_callback=None,     # fn(str)
    cancel_flag=None,         # threading.Event  – set() to abort
) -> dict:
    """
    Compress a video file using FFmpeg H.265.

    Returns:
        {
            "success": bool,
            "original_bytes": int,
            "output_bytes": int,
            "saved_bytes": int,
            "saved_pct": float,
            "output_path": str,
            "error": str | None,
        }
    """

    def _status(msg):
        if status_callback:
            status_callback(msg)

    def _progress(v):
        if progress_callback:
            progress_callback(min(1.0, max(0.0, v)))

    result = {
        "success":        False,
        "original_bytes": 0,
        "output_bytes":   0,
        "saved_bytes":    0,
        "saved_pct":      0.0,
        "output_path":    output_path,
        "error":          None,
    }

    if not os.path.exists(input_path):
        result["error"] = f"File not found: {input_path}"
        return result

    result["original_bytes"] = os.path.getsize(input_path)
    cfg = PRESETS.get(preset_name, PRESETS["Balanced (Recommended)"])

    # ── Get video duration for progress ───────────────────────────────────────
    duration_s = _get_duration(input_path)

    # ── Build FFmpeg command ───────────────────────────────────────────────────
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-c:v", "libx265",
        "-crf", str(cfg["crf"]),
        "-preset", cfg["preset"],
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        "-nostats",
        output_path,
    ]

    _status(f"Compressing with {preset_name}...")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        # Parse FFmpeg progress output
        elapsed_s = 0.0
        for line in proc.stdout:
            line = line.strip()

            if cancel_flag and cancel_flag.is_set():
                proc.kill()
                result["error"] = "Cancelled"
                # Remove partial output
                if os.path.exists(output_path):
                    os.remove(output_path)
                return result

            if line.startswith("out_time_ms="):
                try:
                    elapsed_s = int(line.split("=")[1]) / 1_000_000
                    if duration_s > 0:
                        frac = elapsed_s / duration_s
                        _progress(frac)
                        pct = int(frac * 100)
                        _status(
                            f"Compressing...  {pct}%  "
                            f"({_fmt_time(elapsed_s)} / {_fmt_time(duration_s)})"
                        )
                except (ValueError, ZeroDivisionError):
                    pass

        proc.wait()

        if proc.returncode != 0:
            err = proc.stderr.read() if proc.stderr else "Unknown error"
            result["error"] = f"FFmpeg error (code {proc.returncode})"
            # Clean up failed output
            if os.path.exists(output_path):
                os.remove(output_path)
            return result

    except FileNotFoundError:
        result["error"] = (
            "FFmpeg not found.\n"
            "Please install FFmpeg and add it to PATH.\n"
            "Download: https://ffmpeg.org/download.html"
        )
        return result
    except Exception as e:
        result["error"] = str(e)
        return result

    # ── Calculate savings ─────────────────────────────────────────────────────
    if os.path.exists(output_path):
        out_size = os.path.getsize(output_path)
        orig     = result["original_bytes"]
        saved    = max(0, orig - out_size)
        pct      = (saved / orig * 100) if orig > 0 else 0

        result.update({
            "success":      True,
            "output_bytes": out_size,
            "saved_bytes":  saved,
            "saved_pct":    pct,
        })
        _progress(1.0)
        _status(
            f"Done!  Saved {_fmt_size(saved)}  ({pct:.1f}% smaller)"
        )
    else:
        result["error"] = "Output file was not created."

    return result


def compress_audio(
    input_path: str,
    output_path: str,
    bitrate: str = "128k",
    status_callback=None,
    cancel_flag=None,
) -> dict:
    """Re-encode audio to target bitrate (MP3)."""

    def _status(msg):
        if status_callback:
            status_callback(msg)

    result = {
        "success":        False,
        "original_bytes": os.path.getsize(input_path) if os.path.exists(input_path) else 0,
        "output_bytes":   0,
        "saved_bytes":    0,
        "saved_pct":      0.0,
        "output_path":    output_path,
        "error":          None,
    }

    _status(f"Compressing audio to {bitrate}...")

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-codec:a", "libmp3lame",
        "-b:a", bitrate,
        output_path,
    ]

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)

        while proc.poll() is None:
            if cancel_flag and cancel_flag.is_set():
                proc.kill()
                result["error"] = "Cancelled"
                return result

        if proc.returncode != 0:
            result["error"] = "FFmpeg audio compression failed."
            return result

    except FileNotFoundError:
        result["error"] = "FFmpeg not found."
        return result
    except Exception as e:
        result["error"] = str(e)
        return result

    if os.path.exists(output_path):
        out = os.path.getsize(output_path)
        orig  = result["original_bytes"]
        saved = max(0, orig - out)
        result.update({
            "success":      True,
            "output_bytes": out,
            "saved_bytes":  saved,
            "saved_pct":    (saved / orig * 100) if orig > 0 else 0,
        })
        _status(f"Done!  Saved {_fmt_size(saved)}")

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_duration(path: str) -> float:
    """Return duration in seconds via ffprobe."""
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ], stderr=subprocess.DEVNULL, text=True)
        return float(out.strip())
    except Exception:
        return 0.0


def _fmt_size(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1_048_576:
        return f"{b/1024:.1f} KB"
    if b < 1_073_741_824:
        return f"{b/1_048_576:.1f} MB"
    return f"{b/1_073_741_824:.2f} GB"


def _fmt_time(s: float) -> str:
    s = int(s)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"