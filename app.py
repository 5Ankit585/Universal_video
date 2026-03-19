"""
app.py  —  MediaVault Pro Web Server
Flask backend that powers the browser-based UI.
"""

import os
import json
import threading
import queue
from flask import (Flask, render_template, request, jsonify,
                   send_from_directory, Response, stream_with_context)

from download_manager import DownloadManager
from database import HistoryDB
from settings import Settings
from compressor import compress_video, get_preset_names, get_preset_label
from playlist_fetch import fetch_playlist_info
from updater import update_ytdlp
import ffmpeg_manager

ffmpeg_manager.ensure_on_path()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = "mediavault-pro-2024"

cfg = Settings()

# ── Render: use /tmp/downloads for file storage ───────────────────────────────
if os.environ.get("RENDER"):
    _dl_folder = "/tmp/downloads"
    cfg.set("download_folder", _dl_folder)
    os.makedirs(_dl_folder, exist_ok=True)

# ── SSE event queues ──────────────────────────────────────────────────────────
_dl_events   = queue.Queue()
_comp_events = queue.Queue()

# ── Download Manager ──────────────────────────────────────────────────────────

def _dl_progress(v):
    _dl_events.put({"type": "progress", "value": round(v, 4)})

def _dl_status(msg):
    _dl_events.put({"type": "status", "message": msg})

def _dl_finish(status):
    _dl_events.put({"type": "finish", "status": status})

dm = DownloadManager(
    progress_callback=_dl_progress,
    finish_callback=_dl_finish,
    status_callback=_dl_status,
    download_folder=cfg.get("download_folder") or "downloads",
    settings=cfg,
)

# =============================================================================
# PAGES
# =============================================================================

@app.route("/")
def index():
    return render_template("index.html")

# =============================================================================
# DOWNLOAD API
# =============================================================================

@app.route("/api/download", methods=["POST"])
def api_download():
    data      = request.json or {}
    urls      = data.get("urls", [])
    fmt       = data.get("format", "video")
    quality   = data.get("quality", "best")
    subtitles = data.get("subtitles", False)
    if not urls:
        return jsonify({"error": "No URLs provided"}), 400
    dm.add_to_queue(urls, fmt, quality, subtitles=subtitles)
    return jsonify({"ok": True, "queued": len(urls)})

@app.route("/api/download/cancel", methods=["POST"])
def api_cancel():
    dm.cancel_download()
    return jsonify({"ok": True})

@app.route("/api/download/events")
def api_dl_events():
    def generate():
        while True:
            try:
                event = _dl_events.get(timeout=30)
                yield f"data: {json.dumps(event)}\n\n"
            except queue.Empty:
                yield 'data: {"type":"ping"}\n\n'
    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# =============================================================================
# PLAYLIST API
# =============================================================================

@app.route("/api/playlist/info", methods=["POST"])
def api_playlist_info():
    url = (request.json or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL"}), 400
    result = {"entries": None, "error": None}
    ev     = threading.Event()
    def done(entries, error):
        result["entries"] = entries
        result["error"]   = error
        ev.set()
    fetch_playlist_info(url, done_cb=done)
    ev.wait(timeout=30)
    if result["error"]:
        return jsonify({"error": result["error"]}), 400
    return jsonify({"entries": result["entries"]})

# =============================================================================
# LIBRARY API
# =============================================================================

@app.route("/api/library")
def api_library():
    folder = cfg.get("download_folder") or "downloads"
    exts   = (".mp4", ".mp3", ".mkv", ".webm",
              ".m4a", ".opus", ".wav", ".flac", ".aac")
    files  = []
    if os.path.exists(folder):
        for f in os.listdir(folder):
            if f.lower().endswith(exts):
                path = os.path.join(folder, f)
                files.append({
                    "name":     f,
                    "size":     os.path.getsize(path),
                    "modified": os.path.getmtime(path),
                    "type":     "video" if f.lower().endswith(
                        (".mp4", ".mkv", ".webm")) else "audio",
                })
    sort  = request.args.get("sort", "date")
    query = request.args.get("q", "").lower()
    if query:
        files = [f for f in files if query in f["name"].lower()]
    key_fn = {
        "name": lambda f: f["name"].lower(),
        "size": lambda f: -f["size"],
        "date": lambda f: -f["modified"],
    }.get(sort, lambda f: f["name"].lower())
    files.sort(key=key_fn)
    return jsonify({"files": files})

@app.route("/api/library/stream/<path:filename>")
def api_stream(filename):
    folder = os.path.abspath(cfg.get("download_folder") or "downloads")
    return send_from_directory(folder, filename, as_attachment=False)

@app.route("/api/library/download/<path:filename>")
def api_file_download(filename):
    folder = os.path.abspath(cfg.get("download_folder") or "downloads")
    return send_from_directory(folder, filename, as_attachment=True)

@app.route("/api/library/delete", methods=["POST"])
def api_delete():
    filename = (request.json or {}).get("filename", "")
    folder   = cfg.get("download_folder") or "downloads"
    path     = os.path.join(os.path.abspath(folder), filename)
    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404
    try:
        os.remove(path)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =============================================================================
# SPACE SAVER API
# =============================================================================

@app.route("/api/compress", methods=["POST"])
def api_compress():
    data     = request.json or {}
    filename = data.get("filename", "")
    preset   = data.get("preset", "Balanced (Recommended)")
    replace  = data.get("replace", False)
    folder   = os.path.abspath(cfg.get("download_folder") or "downloads")
    src      = os.path.join(folder, filename)
    if not os.path.exists(src):
        return jsonify({"error": "File not found"}), 404
    name = os.path.splitext(filename)[0]
    dst  = os.path.join(folder, f"{name}_compressed.mp4")
    cancel = threading.Event()
    def run():
        result = compress_video(
            input_path=src, output_path=dst, preset_name=preset,
            progress_callback=lambda v: _comp_events.put(
                {"type": "progress", "value": round(v, 4)}),
            status_callback=lambda m: _comp_events.put(
                {"type": "status", "message": m}),
            cancel_flag=cancel,
        )
        if replace and result.get("success") and os.path.exists(src):
            try:
                os.remove(src)
            except Exception:
                pass
        _comp_events.put({"type": "finish", "result": result})
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/api/compress/events")
def api_comp_events():
    def generate():
        while True:
            try:
                event = _comp_events.get(timeout=30)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "finish":
                    break
            except queue.Empty:
                yield 'data: {"type":"ping"}\n\n'
    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/api/compress/presets")
def api_presets():
    names = get_preset_names()
    return jsonify([{"name": n, "label": get_preset_label(n)} for n in names])

# =============================================================================
# HISTORY API
# =============================================================================

@app.route("/api/history")
def api_history():
    q    = request.args.get("q", "").lower()
    rows = HistoryDB().get_all()
    if q:
        rows = [r for r in rows if q in r[0].lower()]
    return jsonify([
        {"title": r[0], "path": r[1], "type": r[2],
         "quality": r[3], "date": str(r[4])}
        for r in rows])

@app.route("/api/history/clear", methods=["POST"])
def api_history_clear():
    import sqlite3
    with sqlite3.connect("history.db") as c:
        c.execute("DELETE FROM downloads")
    return jsonify({"ok": True})

@app.route("/api/history/export")
def api_history_export():
    import csv, io
    rows   = HistoryDB().get_all()
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["Title", "Path", "Type", "Quality", "Date"])
    w.writerows(rows)
    return Response(
        output.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=history.csv"})

# =============================================================================
# SETTINGS API
# =============================================================================

@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    keys = ["download_folder", "default_quality", "default_format",
            "download_subtitles", "audio_format", "speed_limit_kb",
            "max_retries"]
    return jsonify({k: cfg.get(k) for k in keys})

@app.route("/api/settings", methods=["POST"])
def api_settings_save():
    data = request.json or {}
    for k, v in data.items():
        cfg.set(k, v)
    folder = cfg.get("download_folder") or "downloads"
    os.makedirs(folder, exist_ok=True)
    dm.download_folder = os.path.abspath(folder)
    return jsonify({"ok": True})

# =============================================================================
# FFMPEG + UPDATER
# =============================================================================

@app.route("/api/ffmpeg/status")
def api_ffmpeg_status():
    return jsonify({
        "available": ffmpeg_manager.is_available(),
        "version":   ffmpeg_manager.get_version(),
    })

@app.route("/api/ffmpeg/install", methods=["POST"])
def api_ffmpeg_install():
    result = {"ok": False, "message": ""}
    ev     = threading.Event()
    def done(ok, msg):
        result["ok"]      = ok
        result["message"] = msg
        ev.set()
    ffmpeg_manager.download_ffmpeg(done_cb=done)
    ev.wait(timeout=120)
    return jsonify(result)

@app.route("/api/ytdlp/update", methods=["POST"])
def api_ytdlp_update():
    ok = update_ytdlp()
    return jsonify({"ok": ok,
                    "message": "yt-dlp updated." if ok else "Update failed."})

@app.route("/api/storage")
def api_storage():
    folder = cfg.get("download_folder") or "downloads"
    total  = 0
    count  = 0
    if os.path.exists(folder):
        for f in os.listdir(folder):
            p = os.path.join(folder, f)
            if os.path.isfile(p):
                total += os.path.getsize(p)
                count += 1
    return jsonify({"bytes": total, "count": count})

# =============================================================================
# RUN  ←  THIS IS THE FIXED PART
# =============================================================================

if __name__ == "__main__":
    os.makedirs(cfg.get("download_folder") or "downloads", exist_ok=True)
    port = int(os.environ.get("PORT", 10000))
    print("\n" + "="*52)
    print("  MediaVault Pro  —  Web Interface")
    print(f"  Open in browser:  http://0.0.0.0:{port}")
    print("="*52 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)