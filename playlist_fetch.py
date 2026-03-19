"""
playlist_fetch.py
Fetch playlist / channel metadata using yt-dlp (no download).
"""

import yt_dlp
import threading


def is_playlist(url: str) -> bool:
    """Quick heuristic — full check happens during fetch."""
    kw = ("playlist", "list=", "/channel/", "/c/", "/user/",
          "@", "music.youtube.com/browse")
    return any(k in url.lower() for k in kw)


def fetch_playlist_info(
    url: str,
    done_cb,          # done_cb(entries: list[dict] | None, error: str | None)
    progress_cb=None, # progress_cb(msg: str)
):
    """
    Fetch playlist metadata in a background thread.
    Each entry dict: {title, url, duration, thumbnail, uploader}
    """
    def _run():
        try:
            if progress_cb:
                progress_cb("Fetching playlist info...")

            opts = {
                "quiet":            True,
                "no_warnings":      True,
                "extract_flat":     "in_playlist",
                "skip_download":    True,
                "ignoreerrors":     True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)

            if not info:
                done_cb(None, "Could not fetch info for this URL.")
                return

            # Single video — wrap it
            if info.get("_type") != "playlist":
                entries = [{
                    "title":     info.get("title", "Unknown"),
                    "url":       info.get("webpage_url", url),
                    "duration":  info.get("duration", 0),
                    "thumbnail": info.get("thumbnail", ""),
                    "uploader":  info.get("uploader", ""),
                }]
                done_cb(entries, None)
                return

            entries = []
            for e in (info.get("entries") or []):
                if not e:
                    continue
                entries.append({
                    "title":     e.get("title") or "Unknown",
                    "url":       (e.get("url")
                                  or e.get("webpage_url", "")),
                    "duration":  e.get("duration") or 0,
                    "thumbnail": e.get("thumbnail", ""),
                    "uploader":  e.get("uploader", ""),
                })

            if not entries:
                done_cb(None, "Playlist appears to be empty.")
                return

            done_cb(entries, None)

        except Exception as ex:
            done_cb(None, str(ex))

    threading.Thread(target=_run, daemon=True).start()


def fmt_duration(s):
    if not s:
        return "--:--"
    s = int(s)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"