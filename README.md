# MediaVault Pro

A feature-complete desktop app to download, manage, play, and compress media
from YouTube, playlists, and Spotify — built with Python and CustomTkinter.

---

## Features

| Feature | Details |
|---|---|
| **Download** | YouTube videos, playlists, Spotify tracks |
| **Formats** | Video (MP4) or Audio (MP3, AAC, FLAC, Opus) |
| **Quality** | Best / 1080p / 720p / 480p / 360p |
| **Playlist Preview** | See all videos before downloading, pick what you want |
| **Queue** | Multiple URLs at once with live speed + ETA |
| **Library** | Browse, search, sort your downloads — click to play |
| **Player** | VLC-backed player with seek, volume, speed, loop, fullscreen |
| **Space Saver** | Re-encode with H.265 — save 40–60% disk space |
| **History** | Searchable log of every download + Export to CSV |
| **Settings** | Folder, quality defaults, speed limit, retry count |
| **Theme** | Dark / Light / System — live switch, no restart |
| **Notifications** | Windows toast when downloads complete |
| **FFmpeg installer** | Auto-downloads FFmpeg from Settings if not found |
| **Keyboard shortcuts** | Space, arrows, F11, Escape |

---

## Quick Start

### 1. Install Python 3.10+
Download from https://python.org/downloads
> **Important:** Check "Add Python to PATH" during install

### 2. Install VLC Media Player (64-bit)
Download from https://videolan.org/vlc/
> Must match your Python architecture (64-bit)

### 3. Install dependencies
Open a terminal in the project folder and run:
```
py -m pip install customtkinter yt-dlp python-vlc pillow moviepy spotdl
```

Optional (for Windows toast notifications):
```
py -m pip install win10toast
```

Optional (for drag-and-drop URLs):
```
py -m pip install tkinterdnd2
```

### 4. Install FFmpeg
**Option A — Auto (recommended):**
Run the app, go to **Settings → FFmpeg → Install FFmpeg**
The app will download and configure it automatically.

**Option B — Manual:**
1. Download from https://ffmpeg.org/download.html
2. Extract and add the `bin` folder to your system PATH

### 5. Run
```
py main.py
```

---

## Project Structure

```
MediaVault Pro/
├── main.py              Entry point
├── gui.py               All UI — pages, player, controls
├── download_manager.py  Queue worker + yt-dlp / spotdl
├── compressor.py        FFmpeg H.265 video compression
├── database.py          SQLite download history
├── settings.py          Persistent JSON settings
├── ffmpeg_manager.py    FFmpeg detection + auto-installer
├── notifier.py          Windows toast notifications
├── playlist_fetch.py    Playlist metadata fetcher
├── player.py            VLC wrapper class
├── utils.py             FFmpeg thumbnail generator
├── updater.py           yt-dlp auto-updater
├── mini_player.py       Floating mini player window
├── thumbnail.py         MoviePy thumbnail fallback
├── history.db           SQLite database (auto-created)
├── settings.json        User settings (auto-created)
└── downloads/           Default download folder (auto-created)
```

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Space` | Play / Pause |
| `Right Arrow` | Forward 10 seconds |
| `Left Arrow` | Backward 10 seconds |
| `Up Arrow` | Volume up |
| `Down Arrow` | Volume down |
| `F11` | Toggle fullscreen |
| `Escape` | Exit fullscreen |

> Shortcuts only active when the Library page is open.

---

## Space Saver — How It Works

Uses **FFmpeg + H.265 (HEVC)** to re-encode videos.
H.265 is 2× more efficient than H.264 (the default YouTube codec).

| Preset | Space Saved | Best For |
|---|---|---|
| Maximum Compression | ~60% smaller | Archiving |
| Balanced (default) | ~45% smaller | Everyday use |
| High Quality | ~25% smaller | Important videos |
| Lossless | ~10% smaller | No quality loss |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | Run `py -m pip install <module>` |
| Black video screen | Install 64-bit VLC matching your Python |
| `ffmpeg not found` | Settings → FFmpeg → Install FFmpeg |
| Downloads stop working | Sidebar → Update yt-dlp |
| Spotify not downloading | Run `py -m pip install spotdl` |
| No toast notifications | Run `py -m pip install win10toast` |

---

## Requirements

- Python 3.10+
- VLC Media Player 64-bit
- FFmpeg (auto-installable from Settings)
- Windows 10/11 recommended (works on macOS/Linux with minor limitations)