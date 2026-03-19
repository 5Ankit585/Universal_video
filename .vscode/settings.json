import json
import os

SETTINGS_FILE = "settings.json"

DEFAULTS = {
    "download_folder":    "downloads",
    "default_quality":    "best",
    "default_format":     "video",
    "theme":              "dark",
    "speed_limit_kb":     0,          # 0 = unlimited
    "download_subtitles": False,
    "audio_format":       "mp3",
    "video_format":       "mp4",
    "max_retries":        3,
}


class Settings:
    def __init__(self):
        self._d = dict(DEFAULTS)
        self._load()

    def _load(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    self._d.update(json.load(f))
            except Exception:
                pass

    def save(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._d, f, indent=2)
        except Exception:
            pass

    def get(self, key):
        return self._d.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        self._d[key] = value
        self.save()