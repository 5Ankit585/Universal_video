"""
MediaVault Pro  —  gui.py
Full redesign: Indigo theme, clean icons, dark/light mode, polished UI.
"""

import os
import platform
import threading
import subprocess
import csv
from tkinter import StringVar, BooleanVar, messagebox, END, Menu, filedialog
import customtkinter as ctk
from download_manager import DownloadManager
from database import HistoryDB
from settings import Settings
from notifier import notify
import ffmpeg_manager
ffmpeg_manager.ensure_on_path()

try:
    import vlc
    VLC_AVAILABLE = True
except Exception:
    VLC_AVAILABLE = False

# =============================================================================
# DESIGN TOKENS  —  one place to change the whole look
# =============================================================================

# ── Dark palette ──────────────────────────────────────────────────────────────
D = {
    "bg":        "#0f0f14",
    "surface":   "#16161e",
    "card":      "#1c1c27",
    "border":    "#2a2a3d",
    "hover":     "#252535",
    "input":     "#12121a",

    "accent":    "#6366f1",   # indigo-500
    "accent_h":  "#4f46e5",   # indigo-600
    "accent_lo": "#1e1e3f",   # indigo tint bg

    "green":     "#22c55e",
    "green_h":   "#16a34a",
    "red":       "#ef4444",
    "red_h":     "#dc2626",
    "amber":     "#f59e0b",

    "t1":  "#f1f5f9",   # primary text
    "t2":  "#94a3b8",   # secondary
    "t3":  "#475569",   # muted
    "t4":  "#2d3748",   # very muted

    "ctrl": "#0a0a12",  # player control bar
}

# ── Light palette ─────────────────────────────────────────────────────────────
L = {
    "bg":        "#f0f2f8",
    "surface":   "#e8ebf4",
    "card":      "#ffffff",
    "border":    "#d1d5e8",
    "hover":     "#e2e6f3",
    "input":     "#f8f9ff",

    "accent":    "#6366f1",
    "accent_h":  "#4f46e5",
    "accent_lo": "#eef2ff",

    "green":     "#16a34a",
    "green_h":   "#15803d",
    "red":       "#dc2626",
    "red_h":     "#b91c1c",
    "amber":     "#d97706",

    "t1":  "#0f172a",
    "t2":  "#475569",
    "t3":  "#94a3b8",
    "t4":  "#cbd5e1",

    "ctrl": "#e8ebf4",
}

# Active palette (starts dark, swapped in _apply_theme)
P = dict(D)

# ── Fonts ─────────────────────────────────────────────────────────────────────
FLOGO  = ("Segoe UI", 16, "bold")
FTITLE = ("Segoe UI", 19, "bold")
FHEAD  = ("Segoe UI", 13, "bold")
FBODY  = ("Segoe UI", 12)
FSMALL = ("Segoe UI", 10)
FSYM   = ("Segoe UI Symbol", 13)   # clean transport icons

# ── Clean icon strings (Segoe UI Symbol — renders on all Windows) ─────────────
I_PLAY    = "\u25B6"    # ▶
I_PAUSE   = "\u23F8"    # ⏸  (or use ▐▐)
I_PREV    = "\u23EE"    # ⏮
I_NEXT    = "\u23ED"    # ⏭ (skip)
I_RWD     = "\u23EA"    # ⏪
I_FWD     = "\u23E9"    # ⏩
I_LOOP    = "\u21BA"    # ↺
I_FS      = "\u2922"    # ⤢
I_VOL     = "\u1F50A"   # 🔊  fallback → use text
I_SEARCH  = "\u2315"    # ⌕


# =============================================================================
class App(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.settings = Settings()
        self._theme   = self.settings.get("theme") or "dark"
        ctk.set_appearance_mode(self._theme)
        ctk.set_default_color_theme("blue")

        self.title("MediaVault Pro")
        self.geometry("1440x900")
        self.minsize(1100, 740)

        # runtime state
        self.video_paths    = []
        self.queue_labels   = []
        self._thumb_refs    = []
        self._is_fs         = False
        self._loop          = False
        self._ss_file       = None
        self._ss_running    = False
        self._ss_cancel     = threading.Event()
        self._ss_preset_cells = {}
        self.current_page   = None

        self._apply_theme(self._theme, first=True)
        self._setup_vlc()
        self._setup_manager()
        self._build_root()
        self._show_page("download")
        self._bind_keys()
        self.after(600, self._tick)

    # =========================================================================
    # THEME
    # =========================================================================

    def _apply_theme(self, mode, first=False):
        global P
        self._theme = mode
        P = dict(D if mode == "dark" else L)
        ctk.set_appearance_mode(mode)
        self.settings.set("theme", mode)
        if not first:
            self.configure(fg_color=P["bg"])

    # =========================================================================
    # SETUP
    # =========================================================================

    def _setup_vlc(self):
        self.vlc_instance = self.player = None
        if not VLC_AVAILABLE:
            return
        args = ["--avcodec-hw=none", "--no-video-title-show",
                "--quiet", "--no-osd"]
        if platform.system() == "Windows":
            args.append("--vout=direct3d11")
        try:
            self.vlc_instance = vlc.Instance(*args)
            self.player = self.vlc_instance.media_player_new()
        except Exception:
            pass

    def _setup_manager(self):
        self.dm = DownloadManager(
            progress_callback=self._on_dl_progress,
            finish_callback=self._on_dl_finish,
            status_callback=self._on_dl_status,
            download_folder=self.settings.get("download_folder"),
            settings=self.settings,
        )

    # =========================================================================
    # ROOT LAYOUT
    # =========================================================================

    def _build_root(self):
        self.configure(fg_color=P["bg"])

        self.sidebar = ctk.CTkFrame(
            self, width=230, fg_color=P["surface"],
            corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.content = ctk.CTkFrame(
            self, fg_color=P["bg"], corner_radius=0)
        self.content.pack(side="right", fill="both", expand=True)

        self._build_sidebar()
        self._build_pages()

    # =========================================================================
    # SIDEBAR
    # =========================================================================

    def _build_sidebar(self):
        # ── Logo ──────────────────────────────────────────────────────────────
        logo_wrap = ctk.CTkFrame(
            self.sidebar, fg_color=P["accent"], height=80,
            corner_radius=0)
        logo_wrap.pack(fill="x")
        logo_wrap.pack_propagate(False)
        ctk.CTkLabel(
            logo_wrap, text="MediaVault Pro",
            font=("Segoe UI", 15, "bold"),
            text_color="#ffffff").pack(expand=True)

        # ── Nav ───────────────────────────────────────────────────────────────
        nav_wrap = ctk.CTkFrame(
            self.sidebar, fg_color="transparent")
        nav_wrap.pack(fill="x", padx=12, pady=16)

        self.nav_btns = {}
        nav_items = [
            ("download",   "  Download"),
            ("library",    "  Library"),
            ("spacesaver", "  Space Saver"),
            ("history",    "  History"),
            ("settings",   "  Settings"),
        ]
        for key, label in nav_items:
            btn = ctk.CTkButton(
                nav_wrap, text=label,
                font=FBODY, height=46, anchor="w",
                fg_color="transparent",
                hover_color=P["hover"],
                text_color=P["t2"],
                corner_radius=10,
                command=lambda p=key: self._show_page(p),
            )
            btn.pack(fill="x", pady=2)
            self.nav_btns[key] = btn

        # ── Divider ───────────────────────────────────────────────────────────
        ctk.CTkFrame(
            self.sidebar, height=1,
            fg_color=P["border"]).pack(fill="x", padx=16, pady=8)

        # ── Storage info ──────────────────────────────────────────────────────
        self.storage_lbl = ctk.CTkLabel(
            self.sidebar, text="",
            font=FSMALL, text_color=P["t3"])
        self.storage_lbl.pack(padx=16, pady=(4, 0), anchor="w")
        self._update_storage_info()

        # ── Bottom ────────────────────────────────────────────────────────────
        bottom = ctk.CTkFrame(
            self.sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=12, pady=14)

        ctk.CTkLabel(
            bottom, text="Theme",
            font=FSMALL, text_color=P["t3"]).pack(pady=(0, 4))

        theme_btns = ctk.CTkFrame(
            bottom, fg_color=P["card"], corner_radius=10)
        theme_btns.pack(fill="x")

        self._theme_btn_refs = {}
        for label, val in [("Dark", "dark"),
                            ("Light", "light"),
                            ("System", "system")]:
            b = ctk.CTkButton(
                theme_btns, text=label,
                font=FSMALL, height=34,
                fg_color=P["accent"]
                if self._theme == val else "transparent",
                hover_color=P["accent_h"],
                text_color="#fff" if self._theme == val else P["t2"],
                corner_radius=8,
                command=lambda v=val: self._switch_theme(v),
            )
            b.pack(side="left", fill="x", expand=True, padx=3, pady=3)
            self._theme_btn_refs[val] = b

        ctk.CTkButton(
            bottom, text="Update yt-dlp",
            font=FSMALL, height=32, fg_color="transparent",
            hover_color=P["hover"], text_color=P["t3"],
            command=self._update_ytdlp,
        ).pack(fill="x", pady=(8, 0))

    def _switch_theme(self, val):
        # Stop VLC before rebuild so it doesn't crash
        if self.player:
            try:
                self.player.stop()
            except Exception:
                pass
        self._apply_theme(val)
        for w in self.content.winfo_children():
            w.destroy()
        for w in self.sidebar.winfo_children():
            w.destroy()
        self.sidebar.configure(fg_color=P["surface"])
        self.content.configure(fg_color=P["bg"])
        self._build_sidebar()
        self._build_pages()
        self._show_page(self.current_page or "download")

    def _update_storage_info(self):
        try:
            folder = self.settings.get("download_folder")
            if os.path.exists(folder):
                total = sum(
                    os.path.getsize(os.path.join(folder, f))
                    for f in os.listdir(folder)
                    if os.path.isfile(os.path.join(folder, f))
                )
                self.storage_lbl.configure(
                    text=f"Downloads: {self._sz(total)}")
        except Exception:
            pass

    # =========================================================================
    # PAGES
    # =========================================================================

    def _build_pages(self):
        self.pages = {
            "download":   self._pg_download(),
            "library":    self._pg_library(),
            "spacesaver": self._pg_spacesaver(),
            "history":    self._pg_history(),
            "settings":   self._pg_settings(),
        }

    def _show_page(self, name):
        for f in self.pages.values():
            f.pack_forget()
        for k, b in self.nav_btns.items():
            active = k == name
            b.configure(
                fg_color=P["accent_lo"] if active else "transparent",
                text_color=P["accent"] if active else P["t2"],
                font=("Segoe UI", 12, "bold")
                if active else FBODY,
            )
        self.pages[name].pack(fill="both", expand=True)
        self.current_page = name
        if name == "history":    self._hist_load()
        elif name == "library":  self._lib_load()
        elif name == "spacesaver": self._ss_refresh()

    # =========================================================================
    # DOWNLOAD PAGE
    # =========================================================================

    def _pg_download(self):
        frame = ctk.CTkFrame(self.content, fg_color=P["bg"])

        # ── Page header ───────────────────────────────────────────────────────
        self._page_header(frame, "Download Media",
                          "YouTube  \u00b7  Playlists  \u00b7  Spotify")

        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=28, pady=(0, 24))

        # ── LEFT ──────────────────────────────────────────────────────────────
        lc = ctk.CTkFrame(body, fg_color="transparent")
        lc.pack(side="left", fill="both", expand=True, padx=(0, 14))

        # URL input
        url_card = self._card(lc)
        url_card.pack(fill="x", pady=(0, 10))

        uh = ctk.CTkFrame(url_card, fg_color="transparent")
        uh.pack(fill="x", padx=22, pady=(18, 8))
        ctk.CTkLabel(uh, text="Paste URLs",
                     font=FHEAD, text_color=P["t1"]).pack(side="left")
        ctk.CTkLabel(uh, text="  one per line",
                     font=FSMALL, text_color=P["t3"]).pack(
                         side="left", pady=(3, 0))

        self.url_entry = ctk.CTkTextbox(
            url_card, height=110,
            font=FBODY,
            fg_color=P["input"],
            border_color=P["border"],
            border_width=2,
            text_color=P["t1"],
            corner_radius=10)
        self.url_entry.pack(fill="x", padx=22, pady=(0, 20))
        # ── Drag & drop URLs from browser ────────────────────────────────────
        self.url_entry.drop_target_register = getattr(
            self.url_entry, "drop_target_register", None)
        try:
            self.url_entry.drop_target_register("DND_Text")
            self.url_entry.dnd_bind(
                "<<Drop>>", self._on_url_drop)
        except Exception:
            pass  # tkinterdnd2 not installed — silent fallback

        # Format selector
        fmt_card = self._card(lc)
        fmt_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(fmt_card, text="Format",
                     font=FHEAD, text_color=P["t1"]).pack(
                         anchor="w", padx=22, pady=(18, 10))

        self.format_var = StringVar(
            value=self.settings.get("default_format") or "video")
        frow = ctk.CTkFrame(fmt_card, fg_color="transparent")
        frow.pack(fill="x", padx=22, pady=(0, 18))

        self._fmt_btns = {}
        for label, val, sub in [
            ("Video", "video", "MP4, MKV, WEBM"),
            ("Audio", "audio", "MP3, AAC, FLAC"),
        ]:
            is_sel = self.format_var.get() == val
            cell = ctk.CTkFrame(
                frow,
                fg_color=P["accent"] if is_sel else P["card"],
                corner_radius=14)
            cell.pack(side="left", fill="x", expand=True,
                      padx=(0, 8) if val == "video" else 0)
            ctk.CTkLabel(
                cell, text=label,
                font=("Segoe UI", 13, "bold"),
                text_color="#fff" if is_sel else P["t1"],
            ).pack(anchor="w", padx=16, pady=(14, 2))
            ctk.CTkLabel(
                cell, text=sub,
                font=FSMALL,
                text_color="#c0c0e0" if is_sel else P["t3"],
            ).pack(anchor="w", padx=16, pady=(0, 14))

            def _click(v=val, c=cell):
                self._fmt_select(v)

            cell.bind("<Button-1>", lambda e, fn=_click: fn())
            for ch in cell.winfo_children():
                ch.bind("<Button-1>", lambda e, fn=_click: fn())
            self._fmt_btns[val] = cell

        # Quality + Options
        opt_card = self._card(lc)
        opt_card.pack(fill="x", pady=(0, 10))
        orow = ctk.CTkFrame(opt_card, fg_color="transparent")
        orow.pack(fill="x", padx=22, pady=18)

        # Quality
        qb = ctk.CTkFrame(orow, fg_color="transparent")
        qb.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(qb, text="Quality",
                     font=("Segoe UI", 11, "bold"),
                     text_color=P["t2"]).pack(anchor="w")
        self.quality_var = StringVar(
            value=self.settings.get("default_quality") or "best")
        ctk.CTkOptionMenu(
            qb,
            values=["best", "1080p", "720p", "480p", "360p"],
            variable=self.quality_var,
            font=FBODY, width=145, height=40,
            corner_radius=10,
            fg_color=P["hover"],
            button_color=P["accent"],
            button_hover_color=P["accent_h"],
            dropdown_fg_color=P["card"],
            text_color=P["t1"],
        ).pack(anchor="w", pady=(6, 0))

        # Divider
        ctk.CTkFrame(
            orow, width=1,
            fg_color=P["border"]).pack(
                side="left", fill="y", padx=20)

        # Subtitles
        sb = ctk.CTkFrame(orow, fg_color="transparent")
        sb.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(sb, text="Subtitles",
                     font=("Segoe UI", 11, "bold"),
                     text_color=P["t2"]).pack(anchor="w")
        self.sub_var = BooleanVar(
            value=self.settings.get("download_subtitles"))
        ctk.CTkSwitch(
            sb, text="Download .srt file",
            variable=self.sub_var,
            font=FBODY, text_color=P["t2"],
            progress_color=P["accent"],
        ).pack(anchor="w", pady=(8, 0))

        # Action buttons
        arow = ctk.CTkFrame(lc, fg_color="transparent")
        arow.pack(fill="x", pady=(0, 4))

        self.dl_btn = ctk.CTkButton(
            arow, text="Start Download",
            font=("Segoe UI", 13, "bold"),
            height=50, corner_radius=12,
            fg_color=P["accent"],
            hover_color=P["accent_h"],
            text_color="#ffffff",
            command=self._dl_start,
        )
        self.dl_btn.pack(side="left", fill="x", expand=True,
                         padx=(0, 10))

        self.cancel_btn = ctk.CTkButton(
            arow, text="\u00d7",
            font=("Segoe UI", 18, "bold"),
            width=50, height=50, corner_radius=12,
            fg_color=P["card"],
            hover_color=P["red"],
            text_color=P["t3"],
            state="disabled",
            command=self._dl_cancel,
        )
        self.cancel_btn.pack(side="left")

        self.preview_btn = ctk.CTkButton(
            arow, text="Preview Playlist",
            font=FSMALL, height=50,
            corner_radius=12,
            fg_color=P["card"],
            hover_color=P["accent"],
            text_color=P["t2"],
            command=self._dl_preview_playlist,
        )
        self.preview_btn.pack(side="left", padx=(10, 0))

        # ── RIGHT ─────────────────────────────────────────────────────────────
        rc = ctk.CTkFrame(body, fg_color="transparent", width=315)
        rc.pack(side="right", fill="y")
        rc.pack_propagate(False)

        # Progress card
        pc = self._card(rc)
        pc.pack(fill="x", pady=(0, 10))

        ph = ctk.CTkFrame(pc, fg_color="transparent")
        ph.pack(fill="x", padx=20, pady=(18, 4))
        ctk.CTkLabel(ph, text="Progress",
                     font=FHEAD, text_color=P["t1"]).pack(side="left")
        self.dl_pct = ctk.CTkLabel(
            ph, text="",
            font=("Segoe UI", 13, "bold"),
            text_color=P["accent"])
        self.dl_pct.pack(side="right")

        self.dl_bar = ctk.CTkProgressBar(
            pc, height=6, corner_radius=3,
            fg_color=P["border"],
            progress_color=P["accent"])
        self.dl_bar.pack(fill="x", padx=20, pady=(4, 10))
        self.dl_bar.set(0)

        self.dl_status = ctk.CTkLabel(
            pc,
            text="Ready to download",
            font=FSMALL, text_color=P["t3"],
            wraplength=275, justify="left")
        self.dl_status.pack(anchor="w", padx=20, pady=(0, 18))

        # Queue card
        qc = self._card(rc)
        qc.pack(fill="both", expand=True)

        qh = ctk.CTkFrame(qc, fg_color="transparent")
        qh.pack(fill="x", padx=20, pady=(16, 6))
        ctk.CTkLabel(qh, text="Queue",
                     font=FHEAD, text_color=P["t1"]).pack(side="left")
        self.queue_count = ctk.CTkLabel(
            qh, text="",
            font=FSMALL, text_color=P["t3"])
        self.queue_count.pack(side="right")

        self.queue_scroll = ctk.CTkScrollableFrame(
            qc, fg_color="transparent")
        self.queue_scroll.pack(fill="both", expand=True,
                               padx=8, pady=(0, 10))
        self.empty_q_lbl = ctk.CTkLabel(
            self.queue_scroll,
            text="No items in queue",
            font=FBODY, text_color=P["t3"])
        self.empty_q_lbl.pack(pady=20)

        return frame

    def _fmt_select(self, val):
        self.format_var.set(val)
        for k, cell in self._fmt_btns.items():
            active = k == val
            cell.configure(fg_color=P["accent"] if active else P["card"])
            for ch in cell.winfo_children():
                if isinstance(ch, ctk.CTkLabel):
                    if ch.cget("font")[1] == 13:   # title label
                        ch.configure(
                            text_color="#fff" if active else P["t1"])
                    else:
                        ch.configure(
                            text_color="#c0c0e0"
                            if active else P["t3"])

    # =========================================================================
    # LIBRARY PAGE
    # =========================================================================

    def _pg_library(self):
        frame = ctk.CTkFrame(self.content, fg_color=P["bg"])

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.pack(fill="x", padx=28, pady=(22, 10))
        ctk.CTkLabel(hdr, text="Library & Player",
                     font=FTITLE, text_color=P["t1"]).pack(side="left")
        ctk.CTkButton(
            hdr, text="Refresh", font=FSMALL, height=32,
            fg_color=P["card"], hover_color=P["hover"],
            text_color=P["t2"], corner_radius=8,
            command=self._lib_load,
        ).pack(side="right")

        split = ctk.CTkFrame(frame, fg_color="transparent")
        split.pack(fill="both", expand=True, padx=28, pady=(0, 22))

        # ── File list ─────────────────────────────────────────────────────────
        left = ctk.CTkFrame(
            split, fg_color=P["card"],
            corner_radius=16, width=285)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)

        sr = ctk.CTkFrame(left, fg_color="transparent")
        sr.pack(fill="x", padx=12, pady=(14, 4))

        self.lib_search = ctk.CTkEntry(
            sr,
            placeholder_text="Search files...",
            font=FSMALL,
            fg_color=P["hover"],
            border_color=P["border"],
            text_color=P["t1"], height=34,
            corner_radius=8)
        self.lib_search.pack(side="left", fill="x", expand=True)
        self.lib_search.bind(
            "<KeyRelease>", lambda e: self._lib_load())

        self.sort_var = StringVar(value="Date")
        ctk.CTkOptionMenu(
            sr, values=["Name", "Size", "Date"],
            variable=self.sort_var,
            command=lambda _: self._lib_load(),
            width=74, font=FSMALL,
            fg_color=P["hover"],
            button_color=P["hover"],
            dropdown_fg_color=P["card"],
            text_color=P["t1"],
        ).pack(side="right", padx=(6, 0))

        ctk.CTkFrame(left, height=1,
                     fg_color=P["border"]).pack(
                         fill="x", padx=14, pady=4)

        self.file_scroll = ctk.CTkScrollableFrame(
            left, fg_color="transparent")
        self.file_scroll.pack(fill="both", expand=True,
                              padx=6, pady=(0, 6))

        self.now_pl_lbl = ctk.CTkLabel(
            left, text="",
            font=("Segoe UI", 10, "bold"),
            text_color=P["accent"], wraplength=260)
        self.now_pl_lbl.pack(padx=12, pady=(0, 12))

        # ── Player right panel ────────────────────────────────────────────────
        right = ctk.CTkFrame(
            split, fg_color=P["card"], corner_radius=16)
        right.pack(side="right", fill="both", expand=True)

        self.player_frame = ctk.CTkFrame(
            right, fg_color="#000000", corner_radius=12)
        self.player_frame.pack(fill="both", expand=True,
                               padx=16, pady=(16, 10))
        self.player_frame.bind(
            "<Double-Button-1>", self._pl_toggle_fs)

        self.no_video_lbl = ctk.CTkLabel(
            self.player_frame,
            text="Select a file to start playing\n\n"
                 "Double-click  \u2014  Fullscreen\n"
                 "Space  \u2014  Play / Pause\n"
                 "Arrow keys  \u2014  Seek & Volume",
            font=("Segoe UI", 12),
            text_color="#333344",
            justify="center")
        self.no_video_lbl.place(relx=0.5, rely=0.5, anchor="center")

        # ── Controls bar ──────────────────────────────────────────────────────
        ctrl = ctk.CTkFrame(
            right, fg_color=P["ctrl"], corner_radius=14)
        ctrl.pack(fill="x", padx=16, pady=(0, 16))

        # Track name
        self.track_lbl = ctk.CTkLabel(
            ctrl, text="Nothing playing",
            font=("Segoe UI", 11),
            text_color=P["t3"], anchor="center")
        self.track_lbl.pack(fill="x", padx=20, pady=(14, 6))

        # Seek
        seek_r = ctk.CTkFrame(ctrl, fg_color="transparent")
        seek_r.pack(fill="x", padx=20, pady=(0, 4))

        self.time_cur = ctk.CTkLabel(
            seek_r, text="0:00",
            font=FSMALL, text_color=P["t3"], width=40)
        self.time_cur.pack(side="left")

        self.seek_sl = ctk.CTkSlider(
            seek_r, from_=0, to=100,
            command=self._pl_seek,
            button_color="#ffffff",
            button_hover_color=P["accent"],
            progress_color=P["accent"],
            fg_color=P["border"], height=4)
        self.seek_sl.set(0)
        self.seek_sl.pack(side="left", fill="x",
                          expand=True, padx=10)

        self.time_tot = ctk.CTkLabel(
            seek_r, text="0:00",
            font=FSMALL, text_color=P["t3"], width=40)
        self.time_tot.pack(side="right")

        # Buttons
        btn_r = ctk.CTkFrame(ctrl, fg_color="transparent")
        btn_r.pack(fill="x", padx=20, pady=(6, 16))

        # Left — loop + fullscreen
        lg = ctk.CTkFrame(btn_r, fg_color="transparent")
        lg.pack(side="left", fill="x", expand=True)

        self.loop_btn = ctk.CTkButton(
            lg, text=I_LOOP, width=34, height=34,
            fg_color="transparent",
            hover_color=P["hover"],
            text_color=P["t3"],
            font=("Segoe UI Symbol", 16),
            corner_radius=8,
            command=self._pl_toggle_loop)
        self.loop_btn.pack(side="left", padx=(0, 4))

        self._ctrlbtn(lg, I_FS, self._pl_toggle_fs)

        # Centre — playback
        cg = ctk.CTkFrame(btn_r, fg_color="transparent")
        cg.pack(side="left")

        self._ctrlbtn(cg, I_PREV, self._pl_restart)
        self._ctrlbtn(cg, I_RWD, self._pl_rwd)

        self.pp_btn = ctk.CTkButton(
            cg, text=I_PLAY,
            width=56, height=56, corner_radius=28,
            fg_color="#ffffff",
            hover_color="#e8e8ff",
            text_color=P["accent"],
            font=("Segoe UI Symbol", 20, "bold"),
            command=self._pl_toggle)
        self.pp_btn.pack(side="left", padx=8)

        self._ctrlbtn(cg, I_FWD, self._pl_fwd)
        self._ctrlbtn(cg, I_NEXT, self._pl_restart)   # placeholder

        # Right — vol + speed
        rg = ctk.CTkFrame(btn_r, fg_color="transparent")
        rg.pack(side="right", fill="x", expand=True)

        ctk.CTkLabel(
            rg, text="Vol",
            font=FSMALL, text_color=P["t3"],
        ).pack(side="right", padx=(10, 0))

        self.vol_sl = ctk.CTkSlider(
            rg, from_=0, to=100,
            command=self._pl_vol,
            width=88, height=4,
            button_color="#ffffff",
            button_hover_color=P["accent"],
            progress_color=P["accent"],
            fg_color=P["border"])
        self.vol_sl.set(70)
        self.vol_sl.pack(side="right")
        if self.player:
            self.player.audio_set_volume(70)

        self.speed_menu = ctk.CTkOptionMenu(
            rg,
            values=["0.5x", "0.75x", "1x", "1.25x", "1.5x", "2x"],
            command=self._pl_speed,
            width=72, height=30, font=FSMALL,
            fg_color=P["hover"],
            button_color=P["hover"],
            button_hover_color=P["border"],
            dropdown_fg_color=P["card"],
            text_color=P["t2"])
        self.speed_menu.set("1x")
        self.speed_menu.pack(side="right", padx=(0, 14))

        return frame

    # =========================================================================
    # SPACE SAVER PAGE
    # =========================================================================

    def _pg_spacesaver(self):
        frame = ctk.CTkFrame(self.content, fg_color=P["bg"])

        self._page_header(
            frame,
            "Space Saver",
            "Re-encode with H.265  \u00b7  Save 40-60% disk space",
            accent=P["green"])

        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=28, pady=(0, 24))

        # ── LEFT ──────────────────────────────────────────────────────────────
        lc = ctk.CTkFrame(body, fg_color="transparent")
        lc.pack(side="left", fill="both", expand=True, padx=(0, 14))

        # File selector
        fc = self._card(lc)
        fc.pack(fill="x", pady=(0, 10))

        fh = ctk.CTkFrame(fc, fg_color="transparent")
        fh.pack(fill="x", padx=22, pady=(18, 10))
        ctk.CTkLabel(fh, text="Select File",
                     font=FHEAD, text_color=P["t1"]).pack(side="left")
        ctk.CTkButton(
            fh, text="Browse", width=90, height=32,
            fg_color=P["hover"],
            hover_color=P["accent"],
            text_color=P["t2"], font=FSMALL,
            corner_radius=8,
            command=self._ss_browse,
        ).pack(side="right")

        self.ss_file_lbl = ctk.CTkLabel(
            fc, text="No file selected",
            font=FSMALL, text_color=P["t3"],
            anchor="w", wraplength=480)
        self.ss_file_lbl.pack(fill="x", padx=22, pady=(0, 4))

        sz_row = ctk.CTkFrame(fc, fg_color=P["hover"],
                               corner_radius=10)
        sz_row.pack(fill="x", padx=22, pady=(0, 20))
        self.ss_orig_lbl = ctk.CTkLabel(
            sz_row, text="Original:  —",
            font=FSMALL, text_color=P["t2"])
        self.ss_orig_lbl.pack(side="left", padx=16, pady=10)
        self.ss_est_lbl = ctk.CTkLabel(
            sz_row, text="Estimated output:  —",
            font=("Segoe UI", 10, "bold"),
            text_color=P["green"])
        self.ss_est_lbl.pack(side="right", padx=16)

        # Preset grid
        pc = self._card(lc)
        pc.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(pc, text="Compression Preset",
                     font=FHEAD, text_color=P["t1"]).pack(
                         anchor="w", padx=22, pady=(18, 12))

        from compressor import get_preset_names, get_preset_label, PRESETS
        self.ss_preset_var = StringVar(value="Balanced (Recommended)")
        self._ss_preset_cells = {}

        grid = ctk.CTkFrame(pc, fg_color="transparent")
        grid.pack(fill="x", padx=22, pady=(0, 18))

        ACC_COLORS = {
            "Maximum Compression":    P["green"],
            "Balanced (Recommended)": P["accent"],
            "High Quality":           P["amber"],
            "Lossless":               "#a78bfa",
        }
        for i, name in enumerate(get_preset_names()):
            col, row = i % 2, i // 2
            ac = ACC_COLORS.get(name, P["accent"])
            is_sel = name == self.ss_preset_var.get()

            cell = ctk.CTkFrame(
                grid,
                fg_color=P["accent_lo"] if is_sel else P["hover"],
                corner_radius=12,
                border_width=2 if is_sel else 0,
                border_color=P["accent"] if is_sel else P["hover"])
            cell.grid(row=row, column=col,
                      padx=(0, 8) if col == 0 else 0,
                      pady=(0, 8), sticky="ew")
            grid.columnconfigure(col, weight=1)

            ctk.CTkLabel(
                cell, text=name,
                font=("Segoe UI", 11, "bold"),
                text_color=P["t1"],
            ).pack(anchor="w", padx=14, pady=(12, 2))
            ctk.CTkLabel(
                cell, text=get_preset_label(name),
                font=FSMALL, text_color=ac,
            ).pack(anchor="w", padx=14, pady=(0, 12))

            def click(n=name):
                self._ss_pick(n)

            cell.bind("<Button-1>", lambda e, fn=click: fn())
            for ch in cell.winfo_children():
                ch.bind("<Button-1>", lambda e, fn=click: fn())
            cell.bind("<Enter>",
                      lambda e, c=cell, n=name:
                          c.configure(fg_color=P["accent_lo"]))
            cell.bind("<Leave>",
                      lambda e, c=cell, n=name:
                          c.configure(
                              fg_color=P["accent_lo"]
                              if self.ss_preset_var.get() == n
                              else P["hover"]))

            self._ss_preset_cells[name] = cell

        # Replace toggle
        tog = self._card(lc)
        tog.pack(fill="x", pady=(0, 10))
        ti = ctk.CTkFrame(tog, fg_color="transparent")
        ti.pack(fill="x", padx=22, pady=16)
        tt = ctk.CTkFrame(ti, fg_color="transparent")
        tt.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(tt, text="Replace original file",
                     font=("Segoe UI", 12, "bold"),
                     text_color=P["t1"]).pack(anchor="w")
        ctk.CTkLabel(tt,
                     text="Delete source after compression "
                          "to save extra space",
                     font=FSMALL, text_color=P["t3"]).pack(anchor="w")
        self.ss_replace = BooleanVar(value=False)
        ctk.CTkSwitch(
            ti, text="",
            variable=self.ss_replace,
            progress_color=P["green"],
        ).pack(side="right")

        # Compress button
        self.ss_btn = ctk.CTkButton(
            lc, text="Compress Now",
            font=("Segoe UI", 13, "bold"),
            height=50, corner_radius=12,
            fg_color=P["green"],
            hover_color=P["green_h"],
            text_color="#ffffff",
            command=self._ss_start,
        )
        self.ss_btn.pack(fill="x")

        # ── RIGHT ─────────────────────────────────────────────────────────────
        rc = ctk.CTkFrame(body, fg_color="transparent", width=315)
        rc.pack(side="right", fill="y")
        rc.pack_propagate(False)

        # Progress card
        prg = self._card(rc)
        prg.pack(fill="x", pady=(0, 10))

        ph = ctk.CTkFrame(prg, fg_color="transparent")
        ph.pack(fill="x", padx=20, pady=(18, 4))
        ctk.CTkLabel(ph, text="Progress",
                     font=FHEAD, text_color=P["t1"]).pack(side="left")
        self.ss_pct = ctk.CTkLabel(
            ph, text="",
            font=("Segoe UI", 13, "bold"),
            text_color=P["green"])
        self.ss_pct.pack(side="right")

        self.ss_bar = ctk.CTkProgressBar(
            prg, height=6, corner_radius=3,
            fg_color=P["border"],
            progress_color=P["green"])
        self.ss_bar.pack(fill="x", padx=20, pady=(4, 8))
        self.ss_bar.set(0)

        self.ss_status = ctk.CTkLabel(
            prg, text="Select a video to compress.",
            font=FSMALL, text_color=P["t3"],
            wraplength=275, justify="left")
        self.ss_status.pack(anchor="w", padx=20, pady=(0, 18))

        # Results card
        resc = self._card(rc)
        resc.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(resc, text="Last Result",
                     font=FHEAD, text_color=P["t1"]).pack(
                         anchor="w", padx=20, pady=(16, 8))

        self.ss_r_orig = self._rrow(resc, "Original size", "—")
        self.ss_r_new  = self._rrow(resc, "Compressed", "—")
        self.ss_r_save = self._rrow(resc, "Space saved", "—",
                                     vc=P["green"])
        self.ss_r_pct  = self._rrow(resc, "Reduction", "—",
                                     vc=P["green"])
        ctk.CTkFrame(resc, height=12,
                     fg_color="transparent").pack()

        # Video list card
        vlc2 = self._card(rc)
        vlc2.pack(fill="both", expand=True)

        vh = ctk.CTkFrame(vlc2, fg_color="transparent")
        vh.pack(fill="x", padx=18, pady=(16, 6))
        ctk.CTkLabel(vh, text="Your Videos",
                     font=FHEAD, text_color=P["t1"]).pack(side="left")
        ctk.CTkButton(
            vh, text="Refresh", width=60, height=26,
            fg_color=P["hover"],
            hover_color=P["accent"],
            text_color=P["t3"], font=FSMALL,
            command=self._ss_refresh,
        ).pack(side="right")

        self.ss_list = ctk.CTkScrollableFrame(
            vlc2, fg_color="transparent")
        self.ss_list.pack(fill="both", expand=True,
                          padx=6, pady=(0, 8))

        return frame

    # =========================================================================
    # HISTORY PAGE
    # =========================================================================

    def _pg_history(self):
        frame = ctk.CTkFrame(self.content, fg_color=P["bg"])

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.pack(fill="x", padx=28, pady=(22, 10))
        ctk.CTkLabel(hdr, text="Download History",
                     font=FTITLE, text_color=P["t1"]).pack(side="left")

        bg = ctk.CTkFrame(hdr, fg_color="transparent")
        bg.pack(side="right")
        for label, cmd, hov in [
            ("Export CSV", self._hist_export, P["hover"]),
            ("Clear All", self._hist_clear, P["red"]),
        ]:
            ctk.CTkButton(
                bg, text=label, font=FSMALL, height=32,
                fg_color=P["card"],
                hover_color=hov,
                text_color=P["t2"],
                corner_radius=8, command=cmd,
            ).pack(side="left", padx=(0, 8))

        self.hist_search = ctk.CTkEntry(
            frame,
            placeholder_text="Search history...",
            font=FBODY,
            fg_color=P["card"],
            border_color=P["border"],
            text_color=P["t1"], height=38,
            corner_radius=10)
        self.hist_search.pack(fill="x", padx=28, pady=(0, 8))
        self.hist_search.bind(
            "<KeyRelease>", lambda e: self._hist_load())

        # Column header
        ch = ctk.CTkFrame(frame, fg_color=P["card"],
                          corner_radius=10)
        ch.pack(fill="x", padx=28, pady=(0, 3))
        for text, w in [("Title", 320), ("Type", 70),
                         ("Quality", 80), ("Date", 155),
                         ("Action", 100)]:
            ctk.CTkLabel(
                ch, text=text, font=FHEAD,
                text_color=P["t3"], width=w,
                anchor="w").pack(side="left", padx=14, pady=8)

        self.hist_scroll = ctk.CTkScrollableFrame(
            frame, fg_color="transparent")
        self.hist_scroll.pack(fill="both", expand=True,
                              padx=28, pady=(0, 24))
        return frame

    # =========================================================================
    # SETTINGS PAGE
    # =========================================================================

    def _pg_settings(self):
        frame = ctk.CTkFrame(self.content, fg_color=P["bg"])
        ctk.CTkLabel(frame, text="Settings",
                     font=FTITLE, text_color=P["t1"],
                     ).pack(anchor="w", padx=28, pady=(22, 10))

        sc = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        sc.pack(fill="both", expand=True, padx=28, pady=(0, 24))

        # Folder
        s1 = self._section(sc, "Download Location")
        fr = ctk.CTkFrame(s1, fg_color="transparent")
        fr.pack(fill="x", padx=22, pady=(0, 8))
        self.folder_var = StringVar(
            value=self.settings.get("download_folder") or "downloads")
        ctk.CTkEntry(
            fr, textvariable=self.folder_var,
            font=FBODY,
            fg_color=P["hover"],
            border_color=P["border"],
            text_color=P["t1"], height=38,
            corner_radius=10,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            fr, text="Browse", width=84, height=38,
            fg_color=P["accent"],
            hover_color=P["accent_h"],
            command=self._set_browse,
        ).pack(side="right")
        ctk.CTkButton(
            s1, text="Save", height=36,
            fg_color=P["hover"],
            hover_color=P["accent"],
            text_color=P["t1"],
            corner_radius=8,
            command=self._set_save_folder,
        ).pack(anchor="w", padx=22, pady=(0, 18))

        # Defaults
        s2 = self._section(sc, "Download Defaults")
        self._srow(
            s2, "Default Quality",
            ctk.CTkOptionMenu(
                s2,
                values=["best", "1080p", "720p", "480p", "360p"],
                variable=StringVar(
                    value=self.settings.get("default_quality")
                    or "best"),
                command=lambda v: self.settings.set(
                    "default_quality", v),
                width=130,
                fg_color=P["hover"],
                button_color=P["accent"],
                dropdown_fg_color=P["card"],
                text_color=P["t1"],
            ))
        sub_sw = BooleanVar(
            value=self.settings.get("download_subtitles"))
        self._srow(
            s2, "Download Subtitles",
            ctk.CTkSwitch(
                s2, text="",
                variable=sub_sw,
                progress_color=P["accent"],
                command=lambda: self.settings.set(
                    "download_subtitles", sub_sw.get())))
        self._srow(
            s2, "Audio Format",
            ctk.CTkOptionMenu(
                s2,
                values=["mp3", "aac", "flac", "opus", "m4a"],
                variable=StringVar(
                    value=self.settings.get("audio_format") or "mp3"),
                command=lambda v: self.settings.set(
                    "audio_format", v),
                width=110,
                fg_color=P["hover"],
                button_color=P["accent"],
                dropdown_fg_color=P["card"],
                text_color=P["t1"],
            ))

        # Performance
        s3 = self._section(sc, "Performance")
        spr = ctk.CTkFrame(s3, fg_color="transparent")
        spr.pack(fill="x", padx=22, pady=(0, 4))
        ctk.CTkLabel(
            spr, text="Speed Limit:",
            font=FBODY, text_color=P["t2"],
            width=170, anchor="w").pack(side="left")
        self.spd_lbl = ctk.CTkLabel(
            spr,
            text=self._fmt_spd(
                self.settings.get("speed_limit_kb")),
            font=FBODY, text_color=P["accent"], width=110)
        self.spd_lbl.pack(side="right")
        spd = ctk.CTkSlider(
            s3, from_=0, to=10000,
            command=self._set_spd_change,
            button_color=P["accent"],
            progress_color=P["accent"],
            fg_color=P["border"])
        spd.set(self.settings.get("speed_limit_kb") or 0)
        spd.pack(fill="x", padx=22, pady=(0, 16))
        self._srow(
            s3, "Retries on failure",
            ctk.CTkOptionMenu(
                s3, values=["0", "1", "2", "3", "5"],
                variable=StringVar(
                    value=str(
                        self.settings.get("max_retries") or 3)),
                command=lambda v: self.settings.set(
                    "max_retries", int(v)),
                width=80,
                fg_color=P["hover"],
                button_color=P["accent"],
                dropdown_fg_color=P["card"],
                text_color=P["t1"],
            ))
        ctk.CTkFrame(s3, height=12,
                     fg_color="transparent").pack()

        # FFmpeg section
        s4 = self._section(sc, "FFmpeg")

        ffmpeg_row = ctk.CTkFrame(s4, fg_color="transparent")
        ffmpeg_row.pack(fill="x", padx=22, pady=(0, 8))

        self.ffmpeg_status_lbl = ctk.CTkLabel(
            ffmpeg_row,
            text=self._ffmpeg_status_text(),
            font=FBODY, text_color=P["t2"],
            anchor="w")
        self.ffmpeg_status_lbl.pack(side="left", fill="x",
                                    expand=True)

        self.ffmpeg_btn = ctk.CTkButton(
            ffmpeg_row,
            text="Install FFmpeg" if not ffmpeg_manager.is_available()
                 else "Reinstall",
            font=FSMALL, height=34, width=130,
            fg_color=P["accent"] if not ffmpeg_manager.is_available()
                     else P["hover"],
            hover_color=P["accent_h"],
            text_color="#fff",
            command=self._install_ffmpeg,
        )
        self.ffmpeg_btn.pack(side="right")

        self.ffmpeg_bar = ctk.CTkProgressBar(
            s4, height=5, corner_radius=3,
            fg_color=P["border"],
            progress_color=P["green"])
        self.ffmpeg_bar.pack(fill="x", padx=22, pady=(0, 4))
        self.ffmpeg_bar.set(0)

        self.ffmpeg_info = ctk.CTkLabel(
            s4,
            text="FFmpeg is required for thumbnails, "
                 "audio extraction, and Space Saver.",
            font=FSMALL, text_color=P["t3"],
            wraplength=520, justify="left")
        self.ffmpeg_info.pack(anchor="w", padx=22, pady=(0, 16))

        return frame

    def _ffmpeg_status_text(self):
        if ffmpeg_manager.is_available():
            v = ffmpeg_manager.get_version()
            return f"FFmpeg installed  (v{v})"
        return "FFmpeg not found"

    def _install_ffmpeg(self):
        self.ffmpeg_btn.configure(
            state="disabled", text="Installing...")
        self.ffmpeg_bar.set(0)
        self.ffmpeg_info.configure(
            text="Downloading FFmpeg, please wait...")

        def progress(v):
            self.after(0, lambda x=v: self.ffmpeg_bar.set(x))

        def done(ok, msg):
            def _ui():
                self.ffmpeg_btn.configure(state="normal",
                                          text="Reinstall")
                self.ffmpeg_bar.set(1 if ok else 0)
                self.ffmpeg_status_lbl.configure(
                    text=self._ffmpeg_status_text())
                self.ffmpeg_info.configure(text=msg)
                if ok:
                    notify("MediaVault Pro",
                           "FFmpeg installed successfully!")
            self.after(0, _ui)

        ffmpeg_manager.download_ffmpeg(
            progress_cb=progress, done_cb=done)

    # =========================================================================
    # LIBRARY LOGIC
    # =========================================================================

    def _lib_load(self):
        for w in self.file_scroll.winfo_children():
            w.destroy()
        self.video_paths.clear()
        self._thumb_refs.clear()

        folder = self.settings.get("download_folder") or "downloads"
        exts = (".mp4", ".mp3", ".mkv", ".webm",
                ".m4a", ".opus", ".wav", ".flac", ".aac")
        if not os.path.exists(folder):
            self._elbl(self.file_scroll,
                       "Download folder not found.\nCheck Settings.")
            return

        files = [f for f in os.listdir(folder)
                 if f.lower().endswith(exts)]
        sm = self.sort_var.get()
        key_fn = {
            "Name": lambda f: f.lower(),
            "Size": lambda f: -os.path.getsize(
                os.path.join(folder, f)),
            "Date": lambda f: -os.path.getmtime(
                os.path.join(folder, f)),
        }.get(sm, lambda f: f.lower())
        files.sort(key=key_fn)

        q = self.lib_search.get().lower().strip()
        if q:
            files = [f for f in files if q in f.lower()]

        if not files:
            self._elbl(self.file_scroll,
                       "No media files found."
                       if not q else "No results.")
            return

        for fname in files:
            path = os.path.join(folder, fname)
            self.video_paths.append(path)
            self._lib_card(fname, path)

        self._update_storage_info()

    def _lib_card(self, filename, path):
        is_vid = filename.lower().endswith(
            (".mp4", ".mkv", ".webm"))
        sz = self._sz(os.path.getsize(path))

        card = ctk.CTkFrame(
            self.file_scroll,
            fg_color=P["hover"],
            corner_radius=10, cursor="hand2")
        card.pack(fill="x", pady=3, padx=3)

        inn = ctk.CTkFrame(card, fg_color="transparent")
        inn.pack(fill="x", padx=10, pady=9)

        # Badge
        badge = ctk.CTkLabel(
            inn,
            text="V" if is_vid else "A",
            font=("Segoe UI", 10, "bold"),
            width=32, height=32,
            fg_color=P["accent"] if is_vid else P["green"],
            text_color="#ffffff",
            corner_radius=6)
        badge.pack(side="left")

        # Text
        tb = ctk.CTkFrame(inn, fg_color="transparent")
        tb.pack(side="left", padx=(8, 0), fill="x", expand=True)

        short = filename[:34] + ("..." if len(filename) > 34 else "")
        nl = ctk.CTkLabel(
            tb, text=short, font=FSMALL,
            text_color=P["t1"], anchor="w")
        nl.pack(anchor="w")
        sl = ctk.CTkLabel(
            tb, text=sz,
            font=("Segoe UI", 9), text_color=P["t3"], anchor="w")
        sl.pack(anchor="w")

        if is_vid:
            threading.Thread(
                target=self._lib_thumb,
                args=(path, badge), daemon=True).start()

        def click(e, p=path, f=filename):
            self._lib_play(p, f)

        def rclick(e, p=path, f=filename):
            self._lib_menu(e, p, f)

        for w in ([card, inn, badge, tb]
                  + list(inn.winfo_children())
                  + list(tb.winfo_children())):
            try:
                w.bind("<Button-1>", click)
                w.bind("<Button-3>", rclick)
            except Exception:
                pass

        card.bind("<Enter>",
                  lambda e: card.configure(fg_color=P["border"]))
        card.bind("<Leave>",
                  lambda e: card.configure(fg_color=P["hover"]))

    def _lib_thumb(self, path, lbl):
        try:
            from utils import generate_thumbnail
            img = generate_thumbnail(path)
            if img:
                self._thumb_refs.append(img)
                self.after(0, lambda: lbl.configure(
                    image=img, text="", width=54, height=32,
                    fg_color="transparent", corner_radius=4))
        except Exception:
            pass

    def _lib_menu(self, event, path, filename):
        m = Menu(self, tearoff=0,
                 bg=P["card"], fg=P["t1"],
                 activebackground=P["accent"],
                 activeforeground="#fff",
                 font=("Segoe UI", 11),
                 relief="flat", borderwidth=0)
        m.add_command(label="  Play",
                      command=lambda: self._lib_play(path, filename))
        m.add_separator()
        m.add_command(label="  Open folder",
                      command=lambda: self._lib_open_folder(path))
        m.add_command(label="  Delete file",
                      command=lambda: self._lib_delete(path))
        m.tk_popup(event.x_root, event.y_root)

    def _lib_open_folder(self, path):
        a = os.path.abspath(path)
        if platform.system() == "Windows":
            subprocess.Popen(f'explorer /select,"{a}"')
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-R", a])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(a)])

    def _lib_delete(self, path):
        if messagebox.askyesno(
                "Delete",
                f"Delete '{os.path.basename(path)}'?\n"
                "This cannot be undone."):
            try:
                os.remove(path)
                self._lib_load()
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def _lib_play(self, path, filename):
        if not VLC_AVAILABLE or not self.player:
            messagebox.showerror(
                "VLC Not Found",
                "Install VLC (64-bit) from videolan.org/vlc")
            return
        self.no_video_lbl.place_forget()
        try:
            media = self.vlc_instance.media_new(path)
            self.player.set_media(media)
            if platform.system() == "Windows":
                self.player.set_hwnd(
                    self.player_frame.winfo_id())
            else:
                self.player.set_xwindow(
                    self.player_frame.winfo_id())
            self.player.play()
        except Exception as e:
            messagebox.showerror("Playback Error", str(e))
            return
        self.pp_btn.configure(text=I_PAUSE)
        short = filename[:52] + ("..." if len(filename) > 52 else "")
        self.track_lbl.configure(
            text=short, text_color=P["t2"])
        self.now_pl_lbl.configure(
            text=f"\u25B6  {filename[:36]}")

    # =========================================================================
    # HISTORY LOGIC
    # =========================================================================

    def _hist_load(self):
        for w in self.hist_scroll.winfo_children():
            w.destroy()
        rows = HistoryDB().get_all()
        q = self.hist_search.get().lower().strip()
        if q:
            rows = [r for r in rows if q in r[0].lower()]
        if not rows:
            self._elbl(self.hist_scroll,
                       "No downloads yet." if not q
                       else "No results found.")
            return
        for i, (title, path, ftype, quality, date) in enumerate(rows):
            row = ctk.CTkFrame(
                self.hist_scroll,
                fg_color=P["card"] if i % 2 == 0 else P["hover"],
                corner_radius=8)
            row.pack(fill="x", pady=2)
            tag   = "[V]" if ftype == "video" else "[A]"
            short = (f"{tag}  {title[:48]}"
                     f"{'...' if len(title)>48 else ''}")
            for text, w in [
                (short, 320), (ftype or "-", 70),
                (quality or "-", 80), (str(date)[:16], 155)
            ]:
                ctk.CTkLabel(
                    row, text=text,
                    font=FSMALL, text_color=P["t1"],
                    width=w, anchor="w",
                ).pack(side="left", padx=14, pady=8)
            ex = bool(path and os.path.exists(path))
            ctk.CTkButton(
                row,
                text="Play" if ex else "Gone",
                width=86, height=28, font=FSMALL,
                fg_color=P["accent"] if ex else P["hover"],
                hover_color=P["accent_h"] if ex else P["red"],
                text_color="#fff",
                state="normal" if ex else "disabled",
                command=lambda p=path, t=title:
                    self._hist_play(p, t),
            ).pack(side="left", padx=8)

    def _hist_play(self, path, title):
        self._show_page("library")
        self.after(200, lambda: self._lib_play(path, title))

    def _hist_export(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        rows = HistoryDB().get_all()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(
                ["Title", "Path", "Type", "Quality", "Date"])
            w.writerows(rows)
        messagebox.showinfo("Exported", f"Saved to:\n{path}")

    def _hist_clear(self):
        if messagebox.askyesno(
                "Clear History", "Delete all download history?"):
            import sqlite3
            with sqlite3.connect("history.db") as c:
                c.execute("DELETE FROM downloads")
            self._hist_load()

    # =========================================================================
    # PLAYER CONTROLS
    # =========================================================================

    def _pl_toggle(self):
        if not self.player:
            return
        if self.player.is_playing():
            self.player.pause()
            self.pp_btn.configure(text=I_PLAY)
        else:
            self.player.play()
            self.pp_btn.configure(text=I_PAUSE)

    def _pl_fwd(self):
        if self.player:
            self.player.set_time(self.player.get_time() + 10_000)

    def _pl_rwd(self):
        if self.player:
            self.player.set_time(
                max(0, self.player.get_time() - 10_000))

    def _pl_restart(self):
        if self.player:
            self.player.set_position(0)

    def _pl_seek(self, v):
        if self.player and self.player.get_length() > 0:
            self.player.set_position(float(v) / 100)

    def _pl_vol(self, v):
        if self.player:
            self.player.audio_set_volume(int(v))

    def _pl_vol_up(self):
        v = min(100, int(self.vol_sl.get()) + 5)
        self.vol_sl.set(v)
        self._pl_vol(v)

    def _pl_vol_dn(self):
        v = max(0, int(self.vol_sl.get()) - 5)
        self.vol_sl.set(v)
        self._pl_vol(v)

    def _pl_speed(self, v):
        if self.player:
            self.player.set_rate(float(v.replace("x", "")))

    def _pl_toggle_loop(self):
        self._loop = not self._loop
        self.loop_btn.configure(
            text_color=P["accent"] if self._loop else P["t3"])

    def _pl_toggle_fs(self, event=None):
        self._is_fs = not self._is_fs
        self.attributes("-fullscreen", self._is_fs)

    def _pl_exit_fs(self):
        if self._is_fs:
            self._is_fs = False
            self.attributes("-fullscreen", False)

    def _tick(self):
        try:
            if self.player and self.player.get_length() > 0:
                pos    = self.player.get_position()
                cur    = self.player.get_time()
                length = self.player.get_length()
                self.seek_sl.set(pos * 100)
                self.time_cur.configure(text=self._ms(cur))
                self.time_tot.configure(text=self._ms(length))
                self.pp_btn.configure(
                    text=I_PAUSE
                    if self.player.is_playing() else I_PLAY)
                if (self._loop and pos >= 0.99
                        and not self.player.is_playing()):
                    self.player.set_position(0)
                    self.player.play()
        except Exception:
            pass
        self.after(500, self._tick)

    # =========================================================================
    # KEYBOARD SHORTCUTS
    # =========================================================================

    def _bind_keys(self):
        def lib(fn):
            return lambda e: (fn()
                              if self.current_page == "library"
                              else None)
        self.bind("<space>",  lib(self._pl_toggle))
        self.bind("<Right>",  lib(self._pl_fwd))
        self.bind("<Left>",   lib(self._pl_rwd))
        self.bind("<Up>",     lib(self._pl_vol_up))
        self.bind("<Down>",   lib(self._pl_vol_dn))
        self.bind("<F11>",    lambda e: self._pl_toggle_fs())
        self.bind("<Escape>", lambda e: self._pl_exit_fs())

    # =========================================================================
    # DOWNLOAD CALLBACKS
    # =========================================================================

    def _dl_start(self):
        text = self.url_entry.get("1.0", END).strip()
        if not text:
            messagebox.showwarning("No URL", "Enter at least one URL.")
            return
        urls = [u.strip() for u in text.split("\n") if u.strip()]
        self.dm.add_to_queue(
            urls, self.format_var.get(),
            self.quality_var.get(),
            subtitles=self.sub_var.get())
        self.dl_btn.configure(
            state="disabled", text="Downloading...")
        self.cancel_btn.configure(
            state="normal", text_color=P["t2"])
        self.empty_q_lbl.pack_forget()
        self.queue_count.configure(
            text=f"{len(urls)} item(s)")
        for url in urls:
            short = url[:72] + ("..." if len(url) > 72 else "")
            lbl = ctk.CTkLabel(
                self.queue_scroll,
                text=f"  \u2022  {short}",
                font=FSMALL, text_color=P["t2"], anchor="w")
            lbl.pack(anchor="w", padx=8, pady=2)
            self.queue_labels.append(lbl)

    def _dl_cancel(self):
        self.dm.cancel_download()
        self.cancel_btn.configure(state="disabled")

    def _on_url_drop(self, event):
        """Handle drag-and-drop URL from browser."""
        data = event.data.strip()
        if data:
            self.url_entry.insert(END, data + "\n")

    def _dl_preview_playlist(self):
        """Fetch playlist info and show preview dialog."""
        text = self.url_entry.get("1.0", END).strip()
        if not text:
            messagebox.showwarning("No URL", "Enter a playlist URL first.")
            return
        url = text.split("\n")[0].strip()
        from playlist_fetch import fetch_playlist_info
        self.dl_status.configure(text="Fetching playlist info...")
        self.dl_btn.configure(state="disabled")

        def done(entries, error):
            self.after(0, lambda: self._show_playlist_preview(
                entries, error, url))

        fetch_playlist_info(url, done_cb=done,
                            progress_cb=self._on_dl_status)

    def _show_playlist_preview(self, entries, error, url):
        self.dl_btn.configure(state="normal")
        if error or not entries:
            self.dl_status.configure(
                text=f"Could not fetch: {error or 'No items'}")
            return
        self.dl_status.configure(
            text=f"Found {len(entries)} item(s)")

        # Build popup window
        win = ctk.CTkToplevel(self)
        win.title("Playlist Preview")
        win.geometry("700x540")
        win.configure(fg_color=P["bg"])
        win.grab_set()

        # Header
        hdr = ctk.CTkFrame(win, fg_color=P["surface"], corner_radius=0)
        hdr.pack(fill="x")
        hi = ctk.CTkFrame(hdr, fg_color="transparent")
        hi.pack(fill="x", padx=20, pady=14)
        ctk.CTkLabel(hi, text=f"Playlist  ({len(entries)} videos)",
                     font=FHEAD, text_color=P["t1"]).pack(side="left")

        # Select all / none
        sel_var = BooleanVar(value=True)
        check_vars = []

        def toggle_all():
            v = sel_var.get()
            for cv in check_vars:
                cv.set(v)

        ctk.CTkCheckBox(
            hi, text="Select All",
            variable=sel_var, command=toggle_all,
            font=FSMALL, text_color=P["t2"],
            fg_color=P["accent"]).pack(side="right")

        ctk.CTkFrame(win, height=2,
                     fg_color=P["accent"]).pack(fill="x")

        # Scrollable list
        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=16, pady=10)

        from playlist_fetch import fmt_duration
        for i, entry in enumerate(entries):
            cv = BooleanVar(value=True)
            check_vars.append(cv)

            row = ctk.CTkFrame(scroll,
                               fg_color=P["card"] if i%2==0 else P["hover"],
                               corner_radius=8)
            row.pack(fill="x", pady=2)
            ri = ctk.CTkFrame(row, fg_color="transparent")
            ri.pack(fill="x", padx=12, pady=8)

            ctk.CTkCheckBox(
                ri, text="",
                variable=cv, width=20,
                fg_color=P["accent"],
                hover_color=P["accent_h"],
            ).pack(side="left")

            idx_lbl = ctk.CTkLabel(
                ri, text=f"{i+1:>3}.",
                font=FSMALL, text_color=P["t3"], width=28)
            idx_lbl.pack(side="left", padx=(4, 0))

            title = entry["title"][:62] + ("..." if len(entry["title"]) > 62 else "")
            ctk.CTkLabel(
                ri, text=title,
                font=FSMALL, text_color=P["t1"],
                anchor="w").pack(side="left", fill="x",
                                 expand=True, padx=8)

            dur = fmt_duration(entry.get("duration"))
            ctk.CTkLabel(
                ri, text=dur,
                font=FSMALL, text_color=P["t3"],
                width=52).pack(side="right")

        # Footer
        foot = ctk.CTkFrame(win, fg_color=P["surface"], corner_radius=0)
        foot.pack(fill="x", side="bottom")
        fi = ctk.CTkFrame(foot, fg_color="transparent")
        fi.pack(fill="x", padx=20, pady=14)

        def download_selected():
            selected_urls = [
                entries[i]["url"]
                for i, cv in enumerate(check_vars)
                if cv.get() and entries[i].get("url")
            ]
            if not selected_urls:
                messagebox.showwarning("Nothing selected",
                                       "Select at least one video.")
                return
            # Put selected URLs into the URL entry
            self.url_entry.delete("1.0", END)
            self.url_entry.insert("1.0",
                                  "\n".join(selected_urls))
            win.destroy()
            self._dl_start()

        ctk.CTkButton(
            fi,
            text=f"Download Selected",
            font=("Segoe UI", 13, "bold"),
            height=44, corner_radius=10,
            fg_color=P["accent"],
            hover_color=P["accent_h"],
            command=download_selected,
        ).pack(side="left")

        ctk.CTkButton(
            fi, text="Cancel",
            font=FSMALL, height=44,
            fg_color=P["card"],
            hover_color=P["red"],
            text_color=P["t2"],
            corner_radius=10,
            command=win.destroy,
        ).pack(side="left", padx=10)

        ctk.CTkLabel(
            fi,
            text=f"{len(entries)} total  •  "
                 f"Use checkboxes to select",
            font=FSMALL, text_color=P["t3"],
        ).pack(side="right")

    def _on_dl_progress(self, v):
        self.after(0, lambda x=v: self._dl_set_prog(x))

    def _dl_set_prog(self, v):
        self.dl_bar.set(v)
        self.dl_pct.configure(text=f"{int(v*100)}%")

    def _on_dl_status(self, msg):
        self.after(0, lambda m=msg:
                   self.dl_status.configure(text=m))

    def _on_dl_finish(self, status):
        self.after(0, lambda s=status: self._dl_finish(s))

    def _dl_finish(self, status):
        self.dl_btn.configure(
            state="normal", text="Start Download")
        self.cancel_btn.configure(
            state="disabled", text_color=P["t3"])
        self.dl_bar.set(0)
        self.dl_pct.configure(text="")
        for lbl in self.queue_labels:
            lbl.destroy()
        self.queue_labels.clear()
        self.queue_count.configure(text="")
        self.empty_q_lbl.pack(pady=20)
        self._lib_load()
        msgs = {
            "completed": "All downloads completed.",
            "cancelled": "Download cancelled.",
            "error":     "Download failed. Check URL or update yt-dlp.",
        }
        self.dl_status.configure(text=msgs.get(status, status))
        if status == "completed":
            notify("MediaVault Pro",
                   "Download completed successfully!")
        elif status == "error":
            notify("MediaVault Pro",
                   "Download failed. Check URL or update yt-dlp.")

    # =========================================================================
    # SPACE SAVER LOGIC
    # =========================================================================

    def _ss_pick(self, name):
        self.ss_preset_var.set(name)
        for n, cell in self._ss_preset_cells.items():
            active = n == name
            cell.configure(
                fg_color=P["accent_lo"] if active else P["hover"],
                border_width=2 if active else 0,
                border_color=P["accent"])
        self._ss_estimate()

    def _ss_browse(self):
        path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[
                ("Video", "*.mp4 *.mkv *.webm *.avi *.mov"),
                ("All", "*.*")])
        if path:
            self._ss_set(path)

    def _ss_set(self, path):
        self._ss_file = path
        name  = os.path.basename(path)
        short = name[:56] + ("..." if len(name) > 56 else "")
        self.ss_file_lbl.configure(
            text=short, text_color=P["t2"])
        self.ss_orig_lbl.configure(
            text=f"Original:  {self._sz(os.path.getsize(path))}")
        self._ss_estimate()

    def _ss_estimate(self):
        if not self._ss_file:
            return
        from compressor import PRESETS
        cfg    = PRESETS.get(self.ss_preset_var.get(), {})
        crf    = cfg.get("crf", 24)
        factor = max(0.15, 1.0 - (30 - crf) * 0.025 - 0.25)
        orig   = os.path.getsize(self._ss_file)
        est    = int(orig * factor)
        saved  = orig - est
        self.ss_est_lbl.configure(
            text=f"Estimated:  ~{self._sz(est)}  "
                 f"(save ~{self._sz(saved)})")

    def _ss_refresh(self):
        for w in self.ss_list.winfo_children():
            w.destroy()
        folder = self.settings.get("download_folder") or "downloads"
        exts   = (".mp4", ".mkv", ".webm", ".avi", ".mov")
        if not os.path.exists(folder):
            return
        files = sorted(
            [f for f in os.listdir(folder)
             if f.lower().endswith(exts)],
            key=lambda f: -os.path.getmtime(os.path.join(folder, f)))
        if not files:
            ctk.CTkLabel(
                self.ss_list,
                text="No video files found.",
                font=FSMALL, text_color=P["t3"]).pack(pady=14)
            return
        for fname in files:
            path = os.path.join(folder, fname)
            row  = ctk.CTkFrame(
                self.ss_list, fg_color=P["hover"],
                corner_radius=8, cursor="hand2")
            row.pack(fill="x", pady=3, padx=3)
            inn = ctk.CTkFrame(row, fg_color="transparent")
            inn.pack(fill="x", padx=10, pady=8)
            ctk.CTkLabel(
                inn,
                text=fname[:30] + ("..." if len(fname) > 30 else ""),
                font=FSMALL, text_color=P["t1"],
                anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(
                inn,
                text=self._sz(os.path.getsize(path)),
                font=("Segoe UI", 9), text_color=P["t3"],
            ).pack(side="right")
            for w in [row, inn] + list(inn.winfo_children()):
                w.bind("<Button-1>",
                       lambda e, p=path: self._ss_set(p))
            row.bind("<Enter>",
                     lambda e, r=row: r.configure(
                         fg_color=P["border"]))
            row.bind("<Leave>",
                     lambda e, r=row: r.configure(
                         fg_color=P["hover"]))

    def _ss_start(self):
        if self._ss_running:
            return
        if not self._ss_file:
            messagebox.showwarning("No File",
                                   "Select a video file first.")
            return
        if not os.path.exists(self._ss_file):
            messagebox.showerror("File Not Found",
                                 "The selected file no longer exists.")
            return
        src    = self._ss_file
        name   = os.path.splitext(os.path.basename(src))[0]
        dst    = os.path.join(
            os.path.dirname(src), f"{name}_compressed.mp4")
        if os.path.exists(dst):
            if not messagebox.askyesno(
                    "File Exists", "Overwrite existing output?"):
                return

        self._ss_running = True
        self._ss_cancel.clear()
        self.ss_btn.configure(
            state="disabled", text="Compressing...",
            fg_color=P["hover"])
        self.ss_bar.set(0)
        self.ss_pct.configure(text="")
        self.ss_status.configure(text="Starting...")
        for lbl in [self.ss_r_orig, self.ss_r_new,
                    self.ss_r_save, self.ss_r_pct]:
            lbl.configure(text="—")

        preset  = self.ss_preset_var.get()
        replace = self.ss_replace.get()

        def run():
            from compressor import compress_video
            result = compress_video(
                input_path=src,
                output_path=dst,
                preset_name=preset,
                progress_callback=lambda v: self.after(
                    0, lambda x=v: (
                        self.ss_bar.set(x),
                        self.ss_pct.configure(
                            text=f"{int(x*100)}%"))),
                status_callback=lambda m: self.after(
                    0, lambda s=m:
                        self.ss_status.configure(text=s)),
                cancel_flag=self._ss_cancel,
            )
            self.after(0, lambda: self._ss_done(
                result, src, dst, replace))

        threading.Thread(target=run, daemon=True).start()

    def _ss_done(self, result, src, dst, replace):
        self._ss_running = False
        self.ss_btn.configure(
            state="normal", text="Compress Now",
            fg_color=P["green"])
        if result["error"]:
            messagebox.showerror("Failed", result["error"])
            self.ss_status.configure(
                text=f"Failed: {result['error']}")
            return
        self.ss_r_orig.configure(
            text=self._sz(result["original_bytes"]))
        self.ss_r_new.configure(
            text=self._sz(result["output_bytes"]))
        self.ss_r_save.configure(
            text=self._sz(result["saved_bytes"]))
        self.ss_r_pct.configure(
            text=f"{result['saved_pct']:.1f}% smaller")
        if replace:
            try:
                os.remove(src)
            except Exception:
                pass
        self._ss_refresh()
        self._lib_load()
        self._update_storage_info()
        notify("MediaVault Pro",
               f"Compression done! Saved {self._sz(result['saved_bytes'])} "
               f"({result['saved_pct']:.1f}% smaller)")
        messagebox.showinfo(
            "Compression Complete",
            f"Original:     {self._sz(result['original_bytes'])}\n"
            f"Compressed:  {self._sz(result['output_bytes'])}\n"
            f"Saved:        {self._sz(result['saved_bytes'])} "
            f"({result['saved_pct']:.1f}% smaller)\n\n"
            f"Saved as: {os.path.basename(dst)}")

    # =========================================================================
    # SETTINGS ACTIONS
    # =========================================================================

    def _set_browse(self):
        d = filedialog.askdirectory(title="Select Folder")
        if d:
            self.folder_var.set(d)

    def _set_save_folder(self):
        folder = self.folder_var.get().strip()
        if not folder:
            return
        os.makedirs(folder, exist_ok=True)
        self.settings.set("download_folder", folder)
        self.dm.download_folder = os.path.abspath(folder)
        os.makedirs(self.dm.download_folder, exist_ok=True)
        messagebox.showinfo("Saved", f"Folder set to:\n{folder}")

    def _set_spd_change(self, v):
        val = int(float(v))
        self.settings.set("speed_limit_kb", val)
        self.spd_lbl.configure(text=self._fmt_spd(val))

    def _update_ytdlp(self):
        from updater import update_ytdlp
        self._show_page("download")
        self.dl_status.configure(text="Updating yt-dlp...")

        def run():
            ok  = update_ytdlp()
            msg = ("yt-dlp updated." if ok
                   else "Update failed.")
            self.after(0, lambda: self.dl_status.configure(text=msg))

        threading.Thread(target=run, daemon=True).start()

    # =========================================================================
    # SHARED WIDGET BUILDERS
    # =========================================================================

    def _page_header(self, parent, title, sub, accent=None):
        ac = accent or P["accent"]
        hero = ctk.CTkFrame(parent, fg_color=P["surface"],
                            corner_radius=0)
        hero.pack(fill="x")
        hi = ctk.CTkFrame(hero, fg_color="transparent")
        hi.pack(fill="x", padx=30, pady=(20, 16))
        ctk.CTkLabel(hi, text=title,
                     font=("Segoe UI", 20, "bold"),
                     text_color=P["t1"]).pack(side="left")
        ctk.CTkLabel(hi, text=f"  \u2014  {sub}",
                     font=("Segoe UI", 11),
                     text_color=P["t3"]).pack(
                         side="left", pady=(4, 0))
        ctk.CTkFrame(parent, height=3,
                     fg_color=ac).pack(fill="x")

    def _card(self, parent, r=16):
        return ctk.CTkFrame(
            parent, fg_color=P["card"], corner_radius=r)

    def _section(self, parent, title):
        sec = self._card(parent, r=14)
        sec.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(sec, text=title, font=FHEAD,
                     text_color=P["t1"]).pack(
                         anchor="w", padx=22, pady=(16, 10))
        return sec

    def _srow(self, parent, label, widget):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(0, 12))
        ctk.CTkLabel(row, text=label, font=FBODY,
                     text_color=P["t2"], width=170,
                     anchor="w").pack(side="left")
        widget.pack(side="left")

    def _ctrlbtn(self, parent, text, cmd, w=34, h=34):
        btn = ctk.CTkButton(
            parent, text=text, width=w, height=h,
            fg_color="transparent",
            hover_color=P["hover"],
            text_color=P["t3"],
            font=("Segoe UI Symbol", 14),
            corner_radius=8, command=cmd)
        btn.pack(side="left", padx=2)
        return btn

    def _rrow(self, parent, label, value, vc=None):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=2)
        ctk.CTkLabel(row, text=label, font=FSMALL,
                     text_color=P["t3"], anchor="w",
                     width=130).pack(side="left")
        lbl = ctk.CTkLabel(row, text=value, font=FSMALL,
                           text_color=vc or P["t1"],
                           anchor="e")
        lbl.pack(side="right")
        return lbl

    def _elbl(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=FBODY,
                     text_color=P["t3"],
                     justify="center").pack(pady=24)

    # =========================================================================
    # FORMATTERS
    # =========================================================================

    def _sz(self, b):
        if b < 1024:          return f"{b} B"
        if b < 1_048_576:     return f"{b/1024:.1f} KB"
        if b < 1_073_741_824: return f"{b/1_048_576:.1f} MB"
        return f"{b/1_073_741_824:.2f} GB"

    def _ms(self, ms):
        s = max(0, int(ms / 1000))
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        return f"{h}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"

    def _fmt_spd(self, kb):
        if not kb:
            return "Unlimited"
        return (f"{kb/1024:.1f} MB/s"
                if kb >= 1024 else f"{kb} KB/s")


if __name__ == "__main__":
    app = App()
    app.mainloop()