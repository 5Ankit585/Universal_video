import yt_dlp
import threading
from queue import Queue
import os
import subprocess
import sys
from database import HistoryDB


class DownloadManager:

    def __init__(self, progress_callback=None, finish_callback=None,
                 status_callback=None, download_folder=None, settings=None):
        self.progress_callback = progress_callback
        self.finish_callback   = finish_callback
        self.status_callback   = status_callback
        self.settings          = settings

        self.queue            = Queue()
        self.cancel_requested = False
        self.is_downloading   = False

        self.download_folder = os.path.abspath(download_folder or "downloads")
        os.makedirs(self.download_folder, exist_ok=True)

        self.db = HistoryDB()

        self.worker_thread = threading.Thread(
            target=self._process_queue, daemon=True)
        self.worker_thread.start()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _status(self, msg):
        if self.status_callback:
            self.status_callback(msg)

    def _progress(self, value):
        if self.progress_callback:
            self.progress_callback(min(1.0, max(0.0, float(value))))

    # ── Queue Worker ──────────────────────────────────────────────────────────

    def _process_queue(self):
        while True:
            urls, format_type, quality, subtitles = self.queue.get()
            self.is_downloading   = True
            self.cancel_requested = False

            max_retries = (self.settings.get("max_retries")
                           if self.settings else 3)

            for attempt in range(max_retries + 1):
                try:
                    prefix = (f"Retry {attempt}/{max_retries}...  "
                              if attempt > 0 else "Starting...")
                    self._status(prefix)
                    self._download(urls, format_type, quality, subtitles)

                    if self.cancel_requested:
                        self._status("Cancelled.")
                        if self.finish_callback:
                            self.finish_callback("cancelled")
                    else:
                        self._status("Download complete!")
                        if self.finish_callback:
                            self.finish_callback("completed")
                    break

                except Exception as e:
                    if self.cancel_requested:
                        self._status("Cancelled.")
                        if self.finish_callback:
                            self.finish_callback("cancelled")
                        break
                    if attempt < max_retries:
                        self._status(
                            f"Error - retrying ({attempt+1}/{max_retries})...")
                    else:
                        self._status(f"Failed: {str(e)[:70]}")
                        if self.finish_callback:
                            self.finish_callback("error")

            self.is_downloading = False
            self.queue.task_done()

    # ── Spotify ───────────────────────────────────────────────────────────────

    def _is_spotify(self, url):
        return "spotify.com" in url.lower()

    # ── Main Download ─────────────────────────────────────────────────────────

    def _download(self, urls, format_type, quality="best", subtitles=False):
        if isinstance(urls, str):
            urls = [urls]

        total    = len(urls)
        speed_kb = (self.settings.get("speed_limit_kb")
                    if self.settings else 0) or 0
        audio_fmt = (self.settings.get("audio_format")
                     if self.settings else "mp3") or "mp3"

        for idx, url in enumerate(urls, start=1):
            if self.cancel_requested:
                return

            # ── Spotify ───────────────────────────────────────────────────────
            if self._is_spotify(url):
                self._status(f"[{idx}/{total}] Spotify download...")
                proc = subprocess.Popen(
                    [sys.executable, "-m", "spotdl", url,
                     "--output", self.download_folder],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
                proc.wait()
                if proc.returncode != 0:
                    raise RuntimeError("spotdl failed")
                latest = self._get_latest_file()
                if latest:
                    self._save_history(latest, "audio", "spotify")
                self._progress(idx / total)
                continue

            # ── yt-dlp ────────────────────────────────────────────────────────
            downloaded_files = []

            def progress_hook(d, _i=idx, _t=total):
                if self.cancel_requested:
                    raise Exception("Cancelled")

                if d["status"] == "downloading":
                    tb      = d.get("total_bytes") or d.get("total_bytes_estimate")
                    db_     = d.get("downloaded_bytes", 0)
                    frac    = (db_ / tb) if tb else 0
                    overall = (_i - 1 + frac) / _t
                    self._progress(overall)

                    speed = d.get("speed") or 0
                    eta   = d.get("eta")
                    fname = os.path.basename(d.get("filename", ""))[:38]
                    spd_s = (f"{speed/1_048_576:.1f} MB/s"
                             if speed >= 1_048_576
                             else f"{speed/1024:.0f} KB/s" if speed else "")
                    eta_s = f"ETA {eta}s" if eta else ""
                    parts = [p for p in
                             [f"[{_i}/{_t}]", fname, spd_s, eta_s] if p]
                    self._status("  |  ".join(parts))

                elif d["status"] == "finished":
                    fn = d.get("filename", "")
                    if fn:
                        downloaded_files.append(fn)
                    self._status(f"[{_i}/{_t}] Processing...")
                    self._progress(_i / _t)

            # Common options
            common = {
                "outtmpl":        os.path.join(
                    self.download_folder, "%(title)s.%(ext)s"),
                "progress_hooks": [progress_hook],
                "quiet":          True,
                "no_warnings":    True,
            }
            if speed_kb > 0:
                common["ratelimit"] = speed_kb * 1024
            if subtitles:
                common["writesubtitles"]    = True
                common["writeautomaticsub"] = True
                common["subtitlesformat"]   = "srt"

            if format_type == "video":
                fmt = ("bestvideo+bestaudio/best"
                       if quality == "best"
                       else f"bestvideo[height<={quality.replace('p','')}]"
                            f"+bestaudio/best")
                ydl_opts = {**common,
                            "format": fmt,
                            "merge_output_format": "mp4"}
            else:
                ydl_opts = {**common,
                            "format": "bestaudio/best",
                            "postprocessors": [{
                                "key":              "FFmpegExtractAudio",
                                "preferredcodec":   audio_fmt,
                                "preferredquality": "192",
                            }]}

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            for fp in downloaded_files:
                self._save_history(fp, format_type, quality)

    # ── History ───────────────────────────────────────────────────────────────

    def _save_history(self, file_path, filetype, quality):
        self.db.add_entry(os.path.basename(file_path),
                          file_path, filetype, quality)

    def _get_latest_file(self):
        files = [os.path.join(self.download_folder, f)
                 for f in os.listdir(self.download_folder)]
        return max(files, key=os.path.getctime) if files else None

    # ── Public API ────────────────────────────────────────────────────────────

    def add_to_queue(self, urls, format_type,
                     quality="best", subtitles=False):
        self.queue.put((urls, format_type, quality, subtitles))

    def cancel_download(self):
        self.cancel_requested = True
        self._status("Cancelling...")