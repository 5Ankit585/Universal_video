"""
compressor.py  —  Video compression using FFmpeg
Uses H.264 (libx264) — fast, widely supported, works on Render free tier.
H.265 is too slow for shared hosting — x264 still gives 30-50% savings.
"""

import os
import re
import subprocess
import shutil


# ── Preset definitions ────────────────────────────────────────────────────────
PRESETS = {
    "Maximum Compression":    {"crf": 32, "preset": "faster", "label": "~50% smaller"},
    "Balanced (Recommended)": {"crf": 26, "preset": "fast",   "label": "~35% smaller"},
    "High Quality":           {"crf": 22, "preset": "fast",   "label": "~20% smaller"},
    "Lossless":               {"crf": 18, "preset": "fast",   "label": "~10% smaller"},
}


def get_preset_names():
    return list(PRESETS.keys())


def get_preset_label(name):
    return PRESETS.get(name, {}).get("label", "")


def compress_video(
    input_path: str,
    output_path: str,
    preset_name: str = "Balanced (Recommended)",
    progress_callback=None,
    status_callback=None,
    cancel_flag=None,
) -> dict:

    def _status(msg):
        if status_callback:
            try:
                status_callback(msg)
            except Exception:
                pass

    def _progress(v):
        if progress_callback:
            try:
                progress_callback(min(1.0, max(0.0, float(v))))
            except Exception:
                pass

    result = {
        "success":        False,
        "original_bytes": 0,
        "output_bytes":   0,
        "saved_bytes":    0,
        "saved_pct":      0.0,
        "output_path":    output_path,
        "error":          None,
    }

    # ── Check input file ──────────────────────────────────────────────────────
    if not os.path.exists(input_path):
        result["error"] = f"File not found: {input_path}"
        return result

    result["original_bytes"] = os.path.getsize(input_path)

    # ── Check FFmpeg is available ─────────────────────────────────────────────
    if not shutil.which("ffmpeg"):
        result["error"] = (
            "FFmpeg is not installed on this server.\n"
            "Go to Settings → FFmpeg → Install FFmpeg."
        )
        return result

    cfg = PRESETS.get(preset_name, PRESETS["Balanced (Recommended)"])

    # ── Get duration ──────────────────────────────────────────────────────────
    duration_s = _get_duration(input_path)
    _status(f"Starting compression ({preset_name})...")

    # ── Build FFmpeg command ───────────────────────────────────────────────────
    # Use libx264 — much faster than libx265, works on all servers
    # -progress pipe:2 sends progress to stderr in key=value format
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-c:v", "libx264",
        "-crf", str(cfg["crf"]),
        "-preset", cfg["preset"],
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-progress", "pipe:2",   # progress to stderr
        "-nostats",
        output_path,
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        # ── Parse progress from stderr ────────────────────────────────────────
        for line in proc.stderr:
            line = line.strip()

            # Check for cancel
            if cancel_flag and cancel_flag.is_set():
                proc.kill()
                proc.wait()
                if os.path.exists(output_path):
                    os.remove(output_path)
                result["error"] = "Cancelled"
                return result

            # Parse out_time_ms=12345678
            if line.startswith("out_time_ms="):
                val = line.split("=", 1)[1].strip()
                try:
                    elapsed_s = int(val) / 1_000_000
                    if duration_s > 0 and elapsed_s >= 0:
                        frac = min(elapsed_s / duration_s, 0.99)
                        _progress(frac)
                        pct = int(frac * 100)
                        _status(
                            f"Compressing... {pct}%  "
                            f"({_fmt_time(elapsed_s)} / {_fmt_time(duration_s)})"
                        )
                except (ValueError, ZeroDivisionError):
                    pass

            # Parse out_time=HH:MM:SS.ms  (fallback)
            elif line.startswith("out_time=") and duration_s > 0:
                val = line.split("=", 1)[1].strip()
                try:
                    elapsed_s = _parse_time(val)
                    if elapsed_s >= 0:
                        frac = min(elapsed_s / duration_s, 0.99)
                        _progress(frac)
                except Exception:
                    pass

            # FFmpeg error lines
            elif "Error" in line or "error" in line:
                if "No such file" in line or "Invalid" in line:
                    _status(f"FFmpeg: {line[:80]}")

        proc.wait()

        if proc.returncode not in (0, None):
            result["error"] = (
                f"Compression failed (FFmpeg exit code {proc.returncode}).\n"
                "The video file may be corrupted or an unsupported format."
            )
            if os.path.exists(output_path):
                os.remove(output_path)
            return result

    except FileNotFoundError:
        result["error"] = "FFmpeg not found. Install it from Settings → FFmpeg."
        return result
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"
        return result

    # ── Calculate savings ─────────────────────────────────────────────────────
    if os.path.exists(output_path):
        out_size = os.path.getsize(output_path)
        orig     = result["original_bytes"]
        saved    = max(0, orig - out_size)
        pct      = (saved / orig * 100) if orig > 0 else 0.0

        result.update({
            "success":      True,
            "output_bytes": out_size,
            "saved_bytes":  saved,
            "saved_pct":    round(pct, 1),
        })
        _progress(1.0)
        _status(f"Done!  Saved {_fmt_size(saved)}  ({pct:.1f}% smaller)")
    else:
        result["error"] = "Output file was not created. FFmpeg may have failed silently."

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_duration(path: str) -> float:
    """Get video duration in seconds using ffprobe or ffmpeg fallback."""
    # Try ffprobe first
    if shutil.which("ffprobe"):
        try:
            out = subprocess.check_output(
                ["ffprobe", "-v", "error",
                 "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1",
                 path],
                stderr=subprocess.DEVNULL, text=True, timeout=15)
            val = out.strip()
            if val and val != "N/A":
                return float(val)
        except Exception:
            pass

    # Fallback: use ffmpeg stderr output
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", path],
            stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
            text=True, timeout=15)
        # Parse "Duration: HH:MM:SS.ms"
        match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", result.stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        pass

    return 0.0


def _parse_time(t: str) -> float:
    """Parse HH:MM:SS.ms time string to seconds."""
    try:
        parts = t.strip().split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except Exception:
        return -1.0


def _fmt_size(b: int) -> str:
    if b < 1024:          return f"{b} B"
    if b < 1_048_576:     return f"{b/1024:.1f} KB"
    if b < 1_073_741_824: return f"{b/1_048_576:.1f} MB"
    return f"{b/1_073_741_824:.2f} GB"


def _fmt_time(s: float) -> str:
    s = max(0, int(s))
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"