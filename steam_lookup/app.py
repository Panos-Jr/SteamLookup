\
\
   

import io
import json
import os
import queue as _queue
import shutil
import subprocess
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tkinter import messagebox
from savegd_core import manifest as sg_manifest
from savegd_core import paths as sg_paths
from savegd_core import sync as sg_sync

from . import api, lazy, scrape, steam_ops, ost
from .config import (
    _BASE_DIR, VERSION, ASSETS_DIR, BROWSER_HEADERS,
    BG_DARK, BG_MID, BG_CARD, BG_INPUT, BG_HOVER, BG_SEL,
    ACCENT, ACCENT_DIM, TEXT_PRI, TEXT_SEC, TEXT_MUTED, BORDER,
    COL_FOUND, COL_NOTFOUND, COL_ALWAYS_ONLINE, COL_ANTICHEAT,
    DRM_META, DOWNLOAD_SITES, ONLINE_FIX_SITE, MANUAL_SEARCH_OVERRIDES,
    load_hubcap_key, save_hubcap_key, load_steam_path, save_steam_path,
    load_reminder_state, save_reminder_state,
    TOGGLE_ON, TOGGLE_OFF,
)
from .utils import blend, clean_search_name


                                                                                
class ToggleSwitch(tk.Canvas):
\
\
\
\
       

    def __init__(
        self,
        parent,
        width=48,
        height=26,
        bg=BG_MID,
        on_color=TOGGLE_ON,
        off_color=TOGGLE_OFF,
        knob_color="#ffffff",
        command=None,
        variable=None,
        scale=4,
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )

        self.w = width
        self.h = height
        self.bg = bg

        self.on_color = on_color
        self.off_color = off_color
        self.knob_color = knob_color

        self.command = command
        self.variable = variable

        self.scale = scale
        self._anim_job = None

        self._pad = 2
        self._knob_r = (height - self._pad * 2) / 2

        self._off_x = self._pad + self._knob_r
        self._on_x = width - self._pad - self._knob_r

        self._state = (
            bool(variable.get())
            if variable is not None
            else False
        )

        self._knob_x = self._on_x if self._state else self._off_x

        self._image_id = self.create_image(0, 0, anchor="nw")
        self._photo = None

        self._render()

        self.bind("<Button-1>", self._on_click)
        self.bind("<space>", self._on_click)

        if self.variable is not None:
            self.variable.trace_add("write", self._variable_changed)

    def _render(self):
                                                                  
        Image, ImageTk = lazy.get_pil()
        from PIL import ImageDraw

        S = self.scale
        W = self.w * S
        H = self.h * S

        image = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        pill_color = self.on_color if self._state else self.off_color

        pill_radius = self.h / 2
        draw.rounded_rectangle(
            (0, 0, W, H),
            radius=int(pill_radius * S),
            fill=pill_color,
        )

        r  = self._knob_r
        cx = self._knob_x
        cy = self.h / 2
        draw.ellipse(
            (
                int((cx - r) * S),
                int((cy - r) * S),
                int((cx + r) * S),
                int((cy + r) * S),
            ),
            fill=self.knob_color,
        )

        image = image.resize((self.w, self.h), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(image)
        self.itemconfigure(self._image_id, image=self._photo)

    def _variable_changed(self, *_):
        if self.variable is None:
            return
        new_state = bool(self.variable.get())
        if new_state == self._state:
            return
        self._state = new_state
        self._animate(self._on_x if new_state else self._off_x)

    def _on_click(self, _=None):
        new_state = not self._state
        if self.variable is not None:
            self.variable.set(new_state)
        else:
            self._state = new_state
            self._animate(self._on_x if new_state else self._off_x)
        if self.command:
            self.command()

    def _animate(self, target):
        if self._anim_job is not None:
            try:
                self.after_cancel(self._anim_job)
            except Exception:
                pass
            self._anim_job = None

        start = self._knob_x
        distance = target - start

        if abs(distance) < 0.01:
            self._knob_x = target
            self._render()
            return

        duration = 130
        steps    = 12
        interval = duration // steps

        def step(i=0):
            expected_target = self._on_x if self._state else self._off_x
            if abs(expected_target - target) > 0.01:
                self._anim_job = None
                return
            t = i / steps
            t = 1 - (1 - t) ** 3
            self._knob_x = start + distance * t
            self._render()
            if i < steps:
                self._anim_job = self.after(interval, lambda: step(i + 1))
            else:
                self._knob_x = target
                self._anim_job = None
                self._render()

        step()

    def set_state(self, on: bool):
        on = bool(on)
        if self.variable is not None:
            self.variable.set(on)
        else:
            self._state = on
            self._animate(self._on_x if on else self._off_x)

    def get(self):
        return self._state


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Steam Lookup - Panos Jr")
        self.geometry("1100x720")
        self.minsize(860, 580)
        self.configure(bg=BG_DARK)
        

                                                                           
        self.withdraw()
        splash = self._show_splash()
        self.update()                                      

        self._after_id              = None
        self._drm_cache             = {}
        self._reminder_disabled     = load_reminder_state()
        self._online_fix_request_id = 0
        self.selected_tool          = tk.StringVar(value="Steamtools")
        self.steam_path             = load_steam_path()
        self._appid_name_cache      = {}
        self._popular_games = []                            
        self._popular_page_size = 30
        self._results_limit = 100

                    
        self._popular_page = 0
        self._popular_total = 0
        self._results_limit = 1000
        self._popular_loading = False                                 
        self._popular_filters = {}                                   
        self._disable_ost_var       = None
        self._ost_toggle            = None
        self._stats_label           = None
        self.hubcap_api_key         = load_hubcap_key()
        self._catalog_request_id = 0

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Alt-F4>", lambda e: self._on_close())
        self._build_ui()
        threading.Thread(target=scrape.init_driver_pool, daemon=True).start()
        self.bind_all("<MouseWheel>", self._on_mousewheel)

        self.after(120, lambda: self._finish_splash(splash))
        self.after(200, self._load_popular_page)

    def _show_splash(self):
                                                                
        s = tk.Toplevel(self)
        s.overrideredirect(True)
        s.geometry("320x90+500+400")
        s.configure(bg=BG_DARK)
        s.attributes("-topmost", True)
        try:
            s.attributes("-alpha", 0.95)
        except Exception:
            pass

        tk.Label(s, text="🎮", font=("Segoe UI Emoji", 28),
                 bg=BG_DARK, fg=ACCENT).pack(side="left", padx=(24, 8))
        col = tk.Frame(s, bg=BG_DARK)
        col.pack(side="left", pady=20)
        tk.Label(col, text="Steam Lookup", font=("Segoe UI", 15, "bold"),
                 bg=BG_DARK, fg=TEXT_PRI).pack(anchor="w")
        tk.Label(col, text="Loading…", font=("Segoe UI", 9),
                 bg=BG_DARK, fg=TEXT_MUTED).pack(anchor="w")
        return s

    def _finish_splash(self, splash):
        try:
            splash.destroy()
        except Exception:
            pass
        self.deiconify()

                                                                               
    def _on_mousewheel(self, e):
        try:
            w = self.winfo_containing(e.x_root, e.y_root)
        except Exception:
            return
        while w is not None:
            if isinstance(w, scrape.ScrollFrame):
                w._scroll(e)
                return
            w = getattr(w, "master", None)

                                                                               
    def _build_ui(self):
        hdr = tk.Frame(self, bg=BG_MID, height=64)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="🎮", font=("Segoe UI Emoji", 22),
                 bg=BG_MID, fg=ACCENT).pack(side="left", padx=(18, 8))
        col = tk.Frame(hdr, bg=BG_MID)
        col.pack(side="left")
        tk.Label(col, text="Steam Lookup", font=("Segoe UI", 14, "bold"),
                 bg=BG_MID, fg=TEXT_PRI).pack(anchor="w")
        tk.Label(col, text="Search by game name or App ID — DRM & download sources loaded live",
                 font=("Segoe UI", 9), bg=BG_MID, fg=TEXT_MUTED).pack(anchor="w")

        version_frame = tk.Frame(hdr, bg=BG_MID)
        version_frame.pack(side="right", padx=(0, 18))

        settings_btn = tk.Label(version_frame, text="⚙", font=("Segoe UI Symbol", 15),
                                bg=BG_MID, fg=TEXT_MUTED, cursor="hand2", padx=6)
        settings_btn.pack(side="right")
        settings_btn.bind("<Button-1>", lambda e: self._open_settings())
        settings_btn.bind("<Enter>", lambda e: settings_btn.configure(fg=ACCENT))
        settings_btn.bind("<Leave>", lambda e: settings_btn.configure(fg=TEXT_MUTED))

        restart_hdr_btn = tk.Label(version_frame, text="↻",
                                   font=("Segoe UI Symbol", 16, "bold"),
                                   bg=BG_MID, fg=TEXT_MUTED, cursor="hand2", padx=6)
        restart_hdr_btn.pack(side="right", padx=(0, 4))
        restart_hdr_btn.bind("<Button-1>",
                             lambda e: threading.Thread(
                                 target=self._restart_steam, daemon=True).start())
        restart_hdr_btn.bind("<Enter>", lambda e: restart_hdr_btn.configure(fg=ACCENT))
        restart_hdr_btn.bind("<Leave>", lambda e: restart_hdr_btn.configure(fg=TEXT_MUTED))

        chip = tk.Frame(version_frame, bg=BG_CARD, padx=10, pady=4)
        chip.pack(side="right", padx=(0, 12))
        self.version_label = tk.Label(chip, text=VERSION, font=("Segoe UI", 9, "bold"),
                                      bg=BG_CARD, fg=ACCENT, cursor="hand2")
        self.version_label.pack(side="left")
        self.version_label.bind("<Button-1>", lambda e: self._check_version_click())
        self.outdated_label = tk.Label(chip, text="", font=("Segoe UI", 8, "bold"),
                                       bg=BG_CARD, fg="#ef5350")
        self.outdated_label.pack(side="left", padx=(6, 0))

                                    
        cloud_wrap = tk.Frame(version_frame, bg=BG_CARD, padx=10, pady=4)
        cloud_wrap.pack(side="right", padx=(0, 12))

        self._cloud_btn = tk.Label(
            cloud_wrap,
            text="CloudRedirect",
            font=("Segoe UI", 9, "bold"),
            bg=BG_CARD,
            fg=TEXT_PRI,
            cursor="hand2",
            padx=2,
        )
        self._cloud_btn.pack(side="left")
        self._cloud_btn.bind("<Button-1>", lambda e: self._open_cloudredirect_dialog())
        self._cloud_btn.bind("<Enter>", lambda e: self._cloud_btn.configure(fg=ACCENT))
        self._cloud_btn.bind("<Leave>", lambda e: self._cloud_btn.configure(fg=TEXT_PRI))

                                
        save_sync_wrap = tk.Frame(version_frame, bg=BG_CARD, padx=10, pady=4)
        save_sync_wrap.pack(side="right", padx=(0, 12))

        self._save_sync_btn = tk.Label(
            save_sync_wrap,
            text="💾  Save Sync",
            font=("Segoe UI", 9, "bold"),
            bg=BG_CARD,
            fg=TEXT_PRI,
            cursor="hand2",
            padx=2,
        )
        self._save_sync_btn.pack(side="left")
        self._save_sync_btn.bind("<Button-1>", lambda e: self._launch_save_gd_gui())
        self._save_sync_btn.bind("<Enter>", lambda e: self._save_sync_btn.configure(fg=ACCENT))
        self._save_sync_btn.bind("<Leave>", lambda e: self._save_sync_btn.configure(fg=TEXT_PRI))

                                      
        apply_ost_wrap = tk.Frame(version_frame, bg=BG_CARD, padx=10, pady=4)
        apply_ost_wrap.pack(side="right", padx=(0, 12))

        self._apply_ost_btn = tk.Label(
            apply_ost_wrap,
            text="⚡  Apply OST",
            font=("Segoe UI", 9, "bold"),
            bg=BG_CARD,
            fg=TEXT_PRI,
            cursor="hand2",
            padx=2,
        )
        self._apply_ost_btn.pack(side="left")
        self._apply_ost_btn.bind("<Button-1>", lambda e: self._apply_ost_flow())
        self._apply_ost_btn.bind("<Enter>", lambda e: self._apply_ost_btn.configure(fg=ACCENT))
        self._apply_ost_btn.bind("<Leave>", lambda e: self._apply_ost_btn.configure(fg=TEXT_PRI))

        self.after(100, self._check_version_threaded)

                    
        bar = tk.Frame(self, bg=BG_DARK, pady=12, padx=16)
        bar.pack(fill="x")
        tk.Label(bar, text="🔍", font=("Segoe UI Emoji", 13),
                 bg=BG_DARK, fg=TEXT_MUTED).pack(side="left", padx=(0, 8))
        self._var = tk.StringVar()
        self._var.trace_add("write", self._on_type)
        self._entry = tk.Entry(bar, textvariable=self._var, font=("Segoe UI", 12),
                               bg=BG_INPUT, fg=TEXT_PRI, insertbackground=ACCENT,
                               relief="flat", highlightthickness=1,
                               highlightbackground=BORDER, highlightcolor=ACCENT, bd=6)
        self._entry.pack(
            side="left",
            fill="x",
            expand=True,
            ipady=7
        )

                             
        self._filter_button = tk.Button(
            bar,
            text="☷  Filters",
            command=self._open_filter_popup,
            bg=BG_CARD,
            fg=TEXT_PRI,
            activebackground=BG_HOVER,
            activeforeground=TEXT_PRI,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            bd=0,
            padx=12,
            pady=8,
            cursor="hand2",
        )
        self._filter_button.pack(
            side="left",
            padx=(8, 0)
        )

        self._count_lbl = tk.Label(
            bar,
            text="",
            font=("Segoe UI", 9),
            bg=BG_DARK,
            fg=TEXT_MUTED,
            width=18,
        )
        self._count_lbl.pack(
            side="left",
            padx=(10, 0)
        )

        self._entry.focus()

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill="both", expand=True)
        left = tk.Frame(body, bg=BG_DARK, width=390)
        left.pack(side="left", fill="both")
        left.pack_propagate(False)
        self._list_frame = scrape.ScrollFrame(left, bg=BG_DARK)
        self._list_frame.pack(fill="both", expand=True)
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")
        self._right = tk.Frame(body, bg=BG_DARK)
        self._right.pack(side="left", fill="both", expand=True)
        self._show_placeholder()

                          
        pagination = tk.Frame(self, bg=BG_MID, height=38)
        pagination.pack(fill="x")
        pagination.pack_propagate(False)

        self._prev_page_btn = tk.Button(
            pagination,
            text="‹ Previous",
            command=self._previous_popular_page,
            bg=BG_INPUT,
            fg=TEXT_SEC,
            activebackground=BG_HOVER,
            activeforeground=TEXT_PRI,
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            bd=0,
            padx=12,
            pady=4,
            cursor="hand2",
            state="disabled",
        )
        self._prev_page_btn.pack(side="left", padx=(16, 6), pady=5)

        self._page_label = tk.Label(
            pagination,
            text="Page 1",
            font=("Segoe UI", 8, "bold"),
            bg=BG_MID,
            fg=TEXT_SEC,
        )
        self._page_label.pack(side="left", padx=8)

        self._next_page_btn = tk.Button(
            pagination,
            text="Next ›",
            command=self._next_popular_page,
            bg=BG_INPUT,
            fg=TEXT_SEC,
            activebackground=BG_HOVER,
            activeforeground=TEXT_PRI,
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            bd=0,
            padx=12,
            pady=4,
            cursor="hand2",
            state="disabled",
        )
        self._next_page_btn.pack(side="left", padx=6, pady=5)

                      
        tk.Frame(self, bg=BG_MID, height=1).pack(fill="x")
        self._status = tk.Label(self, text="Ready — type to search", font=("Segoe UI", 9),
                                bg=BG_MID, fg=TEXT_MUTED, anchor="w", padx=16, pady=4)
        self._status.pack(fill="x")

                                                                               
    def _check_version_threaded(self):
        def worker():
            try:
                req = urllib.request.Request(
                    "http://raw.githubusercontent.com/Panos-Jr/SteamLookup/"
                    "refs/heads/main/version.txt",
                    headers=BROWSER_HEADERS)
                with urllib.request.urlopen(req, timeout=5) as r:
                    remote = r.read().decode("utf-8").strip()
                self.after(0, lambda: self._compare_versions(remote))
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _compare_versions(self, remote_version):
        if remote_version and remote_version != VERSION:
            self.version_label.config(fg="#ef5350")
            self.outdated_label.config(text="• OUTDATED")
        else:
            self.version_label.config(fg=ACCENT)
            self.outdated_label.config(text="")

                                                                               
    def _apply_ost_flow(self):
                                                                                 
        if not self.steam_path or not os.path.isdir(self.steam_path):
            messagebox.showerror(
                "Apply OST",
                "Steam folder not set or doesn't exist.\n"
                "Set it in Settings (⚙)."
            )
            return

        if not messagebox.askyesno(
            "Apply OpenSteamTool",
            "This will:\n\n"
            "• Download the OpenSteamTool 1.4.8 release\n"
            "• Extract it\n"
            "• Copy its files into your Steam folder\n"
            "• Restart Steam\n\n"
            "Any existing OpenSteamTool files in the Steam folder "
            "will be replaced.\n\n"
            "Continue?"
        ):
            return

        self._set_status("⚡ Downloading OpenSteamTool…")

        def worker():
            try:
                ok, msg = ost.apply_ost_release(
                    self.steam_path,
                    on_status=lambda t: self.after(0, lambda: self._set_status(t)),
                )
            except Exception as e:
                ok, msg = False, f"Unexpected error: {e}"

            def finish():
                self._set_status(
                    "✅ OpenSteamTool installed" if ok else "❌ OpenSteamTool install failed"
                )
                if ok:
                    if messagebox.askyesno(
                        "Restart Steam",
                        f"{msg}\n\nRestart Steam now?"
                    ):
                        threading.Thread(
                            target=self._restart_steam, daemon=True
                        ).start()
                else:
                    messagebox.showerror("Apply OST", msg)

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

                                                                              
    def _launch_save_gd_gui(self):
                                                           
        from savegd_core import paths as sg_paths

                                                                 
        ok, msg = sg_paths.ensure_runtime_ready()
        if not ok:
            messagebox.showerror("Save Sync", msg)
            return
        
        exe = Path(_BASE_DIR) / "steam_lookup_assets" / "save_gd_gui.exe"               
        if not exe.exists():
            messagebox.showerror(
                "Save Sync",
                f"save_gd_gui.exe not found at:\n{exe}\n\n"
                "Copy it from steam_lookup_assets/ first, or build it with PyInstaller."
            )
            return

        try:
            subprocess.Popen(
                [str(exe)],
                cwd=str(exe.parent),
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                close_fds=True,
            )
        except Exception as e:
            messagebox.showerror("Save Sync", f"Failed to launch: {e}")

    def _open_filter_popup(self):
                                              

                                       
        existing = getattr(self, "_filter_popup", None)

        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.destroy()
                    self._filter_popup = None
                    return
            except tk.TclError:
                pass

        popup = tk.Toplevel(self)
        self._filter_popup = popup

        popup.overrideredirect(True)
        popup.configure(bg=BG_CARD)

        try:
            popup.attributes("-topmost", True)
        except Exception:
            pass

                                                     
        self.update_idletasks()

        x = self._filter_button.winfo_rootx()
        y = (
            self._filter_button.winfo_rooty()
            + self._filter_button.winfo_height()
            + 4
        )

        popup.geometry(f"+{x}+{y}")

                            
        outer = tk.Frame(popup, bg=BORDER, padx=1, pady=1)
        outer.pack(fill="both", expand=True)

        main = tk.Frame(outer, bg=BG_CARD, padx=14, pady=12)
        main.pack(fill="both", expand=True)

                      
        header = tk.Frame(main, bg=BG_CARD)
        header.pack(fill="x", pady=(0, 10))

        tk.Label(
            header,
            text="Filters",
            font=("Segoe UI", 11, "bold"),
            bg=BG_CARD,
            fg=TEXT_PRI,
        ).pack(side="left")

        self._filter_count_label = tk.Label(
            header,
            text="",
            font=("Segoe UI", 8),
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        self._filter_count_label.pack(side="left", padx=(8, 0))

                                 
        if not hasattr(self, "_filter_vars"):
            self._filter_vars = {}

        groups = [
            (
                "Genre",
                [
                    ("⚔️", "Action"),
                    ("🗺️", "Adventure"),
                    ("🎲", "RPG"),
                    ("🔫", "Shooter"),
                    ("🧠", "Strategy"),
                    ("🖥️", "Simulation"),
                    ("🧩", "Puzzle"),
                    ("🏎️", "Racing"),
                    ("🏆", "Sports"),
                ],
            ),
            (
                "Theme",
                [
                    ("👻", "Horror"),
                    ("🌍", "Open World"),
                    ("🏰", "Survival"),
                ],
            ),
            (
                "Players",
                [
                    ("👤", "Singleplayer"),
                    ("👥", "Multiplayer"),
                    ("🤝", "Co-op"),
                    ("🛋️", "Local Co-op"),
                    ("🖥️", "Split Screen"),
                ],
            ),
        ]

        for group_name, items in groups:

            tk.Label(
                main,
                text=group_name,
                font=("Segoe UI", 8, "bold"),
                bg=BG_CARD,
                fg=TEXT_MUTED,
            ).pack(anchor="w", pady=(5, 4))

            grid = tk.Frame(main, bg=BG_CARD)
            grid.pack(fill="x")

            for index, (emoji, name) in enumerate(items):

                if name not in self._filter_vars:
                    self._filter_vars[name] = tk.BooleanVar(value=False)

                var = self._filter_vars[name]

                cb = tk.Checkbutton(
                    grid,
                    text=f"{emoji} {name}",
                    variable=var,
                    bg=BG_CARD,
                    fg=TEXT_PRI,
                    activebackground=BG_CARD,
                    activeforeground=TEXT_PRI,
                    selectcolor=BG_INPUT,
                    font=("Segoe UI", 8),
                    bd=0,
                    highlightthickness=0,
                    padx=5,
                    pady=3,
                    anchor="w",
                    command=self._update_filter_popup_count,
                )

                cb.grid(
                    row=index // 3,
                    column=index % 3,
                    sticky="w",
                    padx=(0, 8),
                )

                               
        bottom = tk.Frame(main, bg=BG_CARD)
        bottom.pack(fill="x", pady=(12, 0))

        clear_btn = tk.Button(
            bottom,
            text="Clear",
            command=self._clear_filters,
            bg=BG_INPUT,
            fg=TEXT_SEC,
            activebackground=BG_HOVER,
            activeforeground=TEXT_PRI,
            font=("Segoe UI", 8),
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
        )
        clear_btn.pack(side="left")

        done_btn = tk.Button(
            bottom,
            text="Apply Filters",
            command=self._apply_filter_popup,
            bg=ACCENT_DIM,
            fg=ACCENT,
            activebackground=blend(ACCENT, alpha=0.3),
            activeforeground=ACCENT,
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            bd=0,
            padx=12,
            pady=4,
            cursor="hand2",
        )
        done_btn.pack(side="right")

        self._update_filter_popup_count()

                                                
        def close_if_outside(event):
            try:
                x1 = popup.winfo_rootx()
                y1 = popup.winfo_rooty()
                x2 = x1 + popup.winfo_width()
                y2 = y1 + popup.winfo_height()

                if not (
                    x1 <= event.x_root <= x2
                    and y1 <= event.y_root <= y2
                ):
                                                                       
                    bx1 = self._filter_button.winfo_rootx()
                    by1 = self._filter_button.winfo_rooty()
                    bx2 = bx1 + self._filter_button.winfo_width()
                    by2 = by1 + self._filter_button.winfo_height()

                    if not (
                        bx1 <= event.x_root <= bx2
                        and by1 <= event.y_root <= by2
                    ):
                        popup.destroy()
                        self._filter_popup = None
            except tk.TclError:
                pass

        self.bind_all("<Button-1>", close_if_outside, add="+")

        def cleanup(_=None):
            try:
                self.unbind_all("<Button-1>")
            except Exception:
                pass

        popup.bind("<Destroy>", cleanup)

                           
        popup.bind(
            "<Escape>",
            lambda e: popup.destroy()
        )

        popup.focus_force()


    def _update_filter_popup_count(self):
                                                   
        count = sum(
            1
            for var in self._filter_vars.values()
            if var.get()
        )

        try:
            if count:
                self._filter_count_label.configure(
                    text=f"{count} selected"
                )
        except (AttributeError, tk.TclError):
            pass


    def _clear_filters(self):
                                                                     

        for var in self._filter_vars.values():
            var.set(False)

        self._update_filter_popup_count()

        self._on_filter_change()

        popup = getattr(self, "_filter_popup", None)

        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass

            self._filter_popup = None


    def _apply_filter_popup(self):
                                                                 

        self._on_filter_change()

        popup = getattr(self, "_filter_popup", None)

        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass

            self._filter_popup = None

    def _on_filter_change(self):
                                                              
        self._popular_page = 0
        self._popular_filters = [
            name
            for name, var in self._filter_vars.items()
            if var.get()
        ]

                                                         
        self._catalog_request_id += 1

        self._popular_games = []
        self._popular_loaded = 0
        self._popular_loading = False

        self._list_frame.clear()

        query = self._var.get().strip()

        if query:
            self._set_status(
                f"Filtering '{query}'…"
            )
        elif self._popular_filters:
            self._set_status(
                "Loading filtered popular games…"
            )
        else:
            self._set_status(
                "Loading popular games…"
            )

        self._count_lbl.configure(text="…")

        self._load_popular_page()

    def _load_popular_page(self):
                                                

        if self._popular_loading:
            return

        self._popular_loading = True

        filters = list(self._popular_filters)
        query = self._var.get().strip()

                                                   
        page = self._popular_page
        page_size = self._popular_page_size

        request_id = self._catalog_request_id

        def worker():
            from . import popular

            try:
                games, total = popular.fetch_games(
                    query=query,
                    page=page,
                    page_size=page_size,
                    tags=filters,
                )

                self.after(
                    0,
                    lambda g=games, t=total, q=query, f=filters, r=request_id:
                        self._on_catalog_page_loaded(
                            g, t, q, f, r
                        ),
                )

            except Exception as exc:
                self.after(
                    0,
                    lambda e=str(exc), r=request_id:
                        self._on_catalog_error(e, r),
                )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

    def _on_catalog_error(self, error, request_id=None):
        if (
            request_id is not None
            and request_id != self._catalog_request_id
        ):
            return

        self._popular_loading = False

        self._list_frame.clear()
        self._count_lbl.configure(text="Error")

        self._set_status(
            f"Steam search error: {error}"
        )

        tk.Label(
            self._list_frame.inner,
            text="⚠️  Couldn't load Steam results",
            font=("Segoe UI", 12, "bold"),
            bg=BG_DARK,
            fg=TEXT_SEC,
        ).pack(pady=(30, 6))

        tk.Label(
            self._list_frame.inner,
            text=str(error),
            font=("Segoe UI", 9),
            bg=BG_DARK,
            fg=TEXT_MUTED,
            wraplength=330,
            justify="center",
        ).pack()


    def _on_catalog_loaded(self, games, total, query, filters):
                                             

        self._list_frame.clear()

        self._popular_games = []
        self._popular_loaded = 0

        self._on_catalog_page_loaded(
            games,
            total,
            query,
            filters,
            self._catalog_request_id,
        )

    def _on_catalog_page_loaded(
        self,
        games,
        total,
        query,
        filters,
        request_id,
    ):
                                        

        if request_id != self._catalog_request_id:
            return

        self._popular_loading = False

                                          
        self._list_frame.clear()
        self._popular_games = list(games)
        self._popular_loaded = len(games)
        self._popular_total = min(total, self._results_limit)

        if not games:
            self._count_lbl.configure(text="No results")

            if filters:
                text = ", ".join(filters)

                if query:
                    self._set_status(
                        f"No results for '{query}' with {text}"
                    )
                else:
                    self._set_status(
                        f"No popular games with {text}"
                    )
            elif query:
                self._set_status(
                    f"No games found for '{query}'"
                )
            else:
                self._set_status(
                    "No popular games found"
                )

            tk.Label(
                self._list_frame.inner,
                text="🔍  No games found",
                font=("Segoe UI", 12, "bold"),
                bg=BG_DARK,
                fg=TEXT_SEC,
            ).pack(pady=30)

            self._update_pagination()
            return

        for game in games:
            self._make_row(game)

        visible_total = min(total, self._results_limit)

        self._count_lbl.configure(
            text=f"{self._popular_loaded} of {visible_total:,}"
        )

        if query:
            base = f"Search: {query}"
        else:
            base = "Popular"

        if filters:
            base += " • " + " • ".join(filters)

        self._set_status(
            f"{base} • showing {self._popular_loaded}"
        )
        self._update_pagination()

    def _total_pages(self):
        if self._popular_total <= 0:
            return 1

        return (
            self._popular_total + self._popular_page_size - 1
        ) // self._popular_page_size

    def _update_pagination(self):
                                             

        total_pages = self._total_pages()
        current = self._popular_page + 1

        try:
            self._page_label.configure(
                text=f"Page {current} of {total_pages}"
            )

            self._prev_page_btn.configure(
                state="normal" if self._popular_page > 0 else "disabled"
            )

            self._next_page_btn.configure(
                state=(
                    "normal"
                    if self._popular_page + 1 < total_pages
                    else "disabled"
                )
            )
        except tk.TclError:
            pass

    def _previous_popular_page(self):
        if self._popular_loading:
            return

        if self._popular_page <= 0:
            return

        self._popular_page -= 1

        self._list_frame.clear()
        self._popular_games = []
        self._popular_loaded = 0

        self._set_status("Loading previous page…")
        self._count_lbl.configure(text="…")

        self._load_popular_page()

    def _next_popular_page(self):
        if self._popular_loading:
            return

        if self._popular_page + 1 >= self._total_pages():
            return

        self._popular_page += 1

        self._list_frame.clear()
        self._popular_games = []
        self._popular_loaded = 0

        self._set_status("Loading next page…")
        self._count_lbl.configure(text="…")

        self._load_popular_page()


    def _on_popular_loaded(self, games, total):
                                                               

        self._popular_loading = False

        if not games:
            if self._popular_loaded == 0:
                if self._popular_filters:
                    self._set_status(
                        "No popular games found for these filters."
                    )
                else:
                    self._set_status(
                        "Couldn't load popular games."
                    )

                self._count_lbl.configure(text="0 results")

            return

        self._popular_games.extend(games)

        for game in games:
            self._make_row(game)

        self._popular_loaded = len(self._popular_games)

        self._count_lbl.configure(
            text=f"{self._popular_loaded} of {total}"
        )

        if self._popular_filters:
            filter_text = ", ".join(self._popular_filters)

            self._set_status(
                f"Popular • {filter_text}"
            )
        else:
            self._set_status(
                f"Showing {self._popular_loaded} popular games"
            )


    def _check_version_click(self):
        if self.outdated_label.cget("text") == "• OUTDATED":
            try:
                req = urllib.request.Request(
                    "https://raw.githubusercontent.com/Panos-Jr/SteamLookup/"
                    "refs/heads/main/download.txt",
                    headers=BROWSER_HEADERS)
                with urllib.request.urlopen(req, timeout=5) as r:
                    __import__("webbrowser").open(r.read().decode("utf-8").strip())
            except Exception:
                pass

                                                                               
    def _on_type(self, *_):
        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = self.after(350, self._search)

    def _search(self):
        q = self._var.get().strip()

                                                       
        self._popular_page = 0
        self._catalog_request_id += 1

        self._popular_games = []
        self._popular_loaded = 0
        self._popular_loading = False

        self._list_frame.clear()

        if not q or len(q) < 2:
            self._count_lbl.configure(text="")

            if self._popular_filters:
                self._set_status(
                    "Loading filtered popular games…"
                )
            else:
                self._set_status(
                    "Loading popular games…"
                )

            self._load_popular_page()
            return

                         
        if q.isdigit():
            appid = int(q)

            game = {
                "appid": appid,
                "name": f"App ID {appid}",
            }

            self._count_lbl.configure(text="1 result")
            self._make_row(game)
            self._show_detail(game)

            self._set_status(
                f"Showing App ID {appid}"
            )
            return

                                           
        filters = list(self._popular_filters)

        self._set_status(
            f"Searching '{q}'…"
        )
        self._count_lbl.configure(text="…")

                                                          
        self._load_popular_page()

    def _on_results(self, games, total=None):
        self._list_frame.clear()
        n     = len(games)
        shown = total if (total and total > n) else n
        if n == 0:
            self._count_lbl.configure(text="No results")
            self._set_status("No games found")
            tk.Label(self._list_frame.inner, text="🔍  No games found",
                     font=("Segoe UI", 12, "bold"), bg=BG_DARK, fg=TEXT_SEC).pack(pady=30)
            tk.Label(self._list_frame.inner,
                     text="Try a different name or paste the numeric App ID",
                     font=("Segoe UI", 9), bg=BG_DARK, fg=TEXT_MUTED).pack()
            return
        label = (f"Showing {n} of {shown}" if shown > n
                 else f"{n} result{'s' if n != 1 else ''}")
        self._count_lbl.configure(text=label)
        self._set_status(f"{shown} match{'es' if shown != 1 else ''} found")
        for g in games:
            self._make_row(g)

    def _make_row(self, game):
        appid = game["appid"]
        row   = tk.Frame(self._list_frame.inner, bg=BG_DARK, cursor="hand2")
        row.pack(fill="x")
        row._sel = False

        accent_bar = tk.Frame(row, bg=BG_DARK, width=3)
        accent_bar.pack(side="left", fill="y")
        body = tk.Frame(row, bg=BG_DARK, padx=12, pady=10)
        body.pack(side="left", fill="x", expand=True)

        name_lbl = tk.Label(body, text=game["name"], font=("Segoe UI", 10, "bold"),
                            bg=BG_DARK, fg=TEXT_PRI, anchor="w",
                            wraplength=260, justify="left")
        name_lbl.pack(anchor="w")
        id_lbl = tk.Label(body, text=f"App ID: {appid}", font=("Segoe UI", 8),
                          bg=BG_DARK, fg=TEXT_MUTED, anchor="w")
        id_lbl.pack(anchor="w")
        badge = tk.Label(body, text=" ⏳ Loading DRM… ", font=("Segoe UI", 8, "bold"),
                         bg=blend(DRM_META["loading"][0]),
                         fg=DRM_META["loading"][0], pady=2)
        badge.pack(anchor="w", pady=(4, 0))

        tk.Frame(self._list_frame.inner, bg=BORDER, height=1).pack(fill="x")

        bg_widgets = [row, accent_bar, body, name_lbl, id_lbl]

        def enter(_):
            for w in bg_widgets:
                try: w.configure(bg=BG_HOVER)
                except Exception: pass

        def leave(_):
            bg = BG_SEL if row._sel else BG_DARK
            for w in bg_widgets:
                try: w.configure(bg=bg)
                except Exception: pass

        def click(_):
            self._show_detail(game)
            for sibling in self._list_frame.inner.winfo_children():
                if hasattr(sibling, "_sel"):
                    sibling._sel = False
                    sibling.configure(bg=BG_DARK)
                    for c in sibling.winfo_children():
                        try: c.configure(bg=BG_DARK)
                        except Exception: pass
            row._sel = True
            for w in bg_widgets:
                try: w.configure(bg=BG_SEL)
                except Exception: pass
            try: accent_bar.configure(bg=ACCENT)
            except Exception: pass

        for w in [row, accent_bar, body, name_lbl, id_lbl, badge]:
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)
            w.bind("<Button-1>", click)

        def fetch_and_patch():
            drm = self._drm_cache.get(appid) or api.get_drm(appid)
            self._drm_cache[appid] = drm

            def patch():
                try:
                    badge.configure(text=f" {drm['icon']} {drm['label']} ",
                                    bg=blend(drm["color"]), fg=drm["color"])
                except tk.TclError:
                    pass
            self.after(0, patch)

        threading.Thread(target=fetch_and_patch, daemon=True).start()

                                                                               
    def _show_placeholder(self):
        for w in self._right.winfo_children():
            w.destroy()
        ph = tk.Frame(self._right, bg=BG_DARK)
        ph.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(ph, text="🎮", font=("Segoe UI Emoji", 48),
                 bg=BG_DARK, fg=TEXT_MUTED).pack()
        tk.Label(ph, text="Select a game to view DRM & download sources",
                 font=("Segoe UI", 12), bg=BG_DARK, fg=TEXT_MUTED).pack(pady=(8, 0))

    def _show_detail(self, game):
        self._online_fix_request_id += 1
        current_request_id = self._online_fix_request_id
        for w in self._right.winfo_children():
            w.destroy()
        tk.Label(self._right, text="Loading…", font=("Segoe UI", 11),
                 bg=BG_DARK, fg=TEXT_MUTED).pack(expand=True)
        appid = game["appid"]

        def worker():
            info = api.steam_appdetails(appid)
            drm = self._drm_cache.get(appid) or api.get_drm(appid)
            self._drm_cache[appid] = drm
            self.after(0, lambda i=info, d=drm: self._render_detail(
                game, i, d, current_request_id))

        threading.Thread(target=worker, daemon=True).start()

    def _render_detail(self, game, info, drm, request_id):
        if request_id != self._online_fix_request_id:
            return
        for w in self._right.winfo_children():
            w.destroy()

        sf = scrape.ScrollFrame(self._right, bg=BG_DARK)
        sf.pack(fill="both", expand=True)
        p = sf.inner

        hero_frame = tk.Frame(p, bg=BG_MID, height=220)
        hero_frame.pack(fill="x")
        hero_frame.pack_propagate(False)
        hero_lbl = tk.Label(hero_frame, bg=BG_MID, text="Loading image...",
                            fg=TEXT_MUTED, font=("Segoe UI", 12))
        hero_lbl.pack(fill="both", expand=True)
        img_request_id       = object()
        hero_lbl._request_id = img_request_id

        def load_img():
            try:
                data = api.steam_appdetails(game["appid"])
                img_url = (data or {}).get("header_image")
                if not img_url:
                    return
                img_bytes = api.download_image_bytes(img_url, timeout=10)
                Image, ImageTk = lazy.get_pil()
                pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
                pil_img = pil_img.resize((540, 220), Image.Resampling.LANCZOS)
            except Exception:
                return

            def apply_image():
                try:
                    if getattr(hero_lbl, "_request_id", None) is not img_request_id:
                        return
                    img = ImageTk.PhotoImage(pil_img)
                    hero_lbl.image = img
                    hero_lbl.configure(image=img, text="")
                except tk.TclError:
                    pass
            self.after(0, apply_image)

        threading.Thread(target=load_img, daemon=True).start()

        c = tk.Frame(p, bg=BG_DARK, padx=20, pady=16)
        c.pack(fill="both", expand=True)

        name              = info.get("name", game["name"]) if info else game["name"]
        clean_name        = clean_search_name(name)
        for steam_name, search_term in MANUAL_SEARCH_OVERRIDES.items():
            if (steam_name.lower() in name.lower()
                    or steam_name.lower() in clean_name.lower()):
                clean_name = search_term
                self._set_status(f"🔄 Override: using '{search_term}' for download checks")
                break

        tk.Label(c, text=name, font=("Segoe UI", 16, "bold"),
                 bg=BG_DARK, fg=TEXT_PRI, wraplength=480,
                 justify="left").pack(anchor="w")

        appid_frame = tk.Frame(c, bg=BG_DARK)
        appid_frame.pack(anchor="w", fill="x", pady=(2, 14))
        tk.Label(appid_frame, text=f"App ID: {game['appid']}",
                 font=("Segoe UI", 9), bg=BG_DARK, fg=TEXT_MUTED).pack(side="left")
        copy_btn = tk.Label(appid_frame, text="📋 Copy", font=("Segoe UI", 9),
                            bg=BG_DARK, fg=TEXT_MUTED, cursor="hand2")
        copy_btn.pack(side="left", padx=(8, 0))

        def copy_to_clipboard():
            self.clipboard_clear()
            self.clipboard_append(str(game['appid']))
            orig = copy_btn.cget("text")
            copy_btn.config(text="✓ Copied!", fg=ACCENT)

            def restore():
                try: copy_btn.config(text=orig, fg=TEXT_MUTED)
                except tk.TclError: pass
            self.after(2000, restore)

        copy_btn.bind("<Button-1>", lambda e: copy_to_clipboard())
        copy_btn.bind("<Enter>", lambda e: copy_btn.config(fg=ACCENT))
        copy_btn.bind("<Leave>", lambda e: copy_btn.config(fg=TEXT_MUTED))

        drm_f = tk.Frame(c, bg=BG_CARD)
        drm_f.pack(fill="x", pady=(0, 14))
        tk.Frame(drm_f, bg=drm["color"], width=4).pack(side="left", fill="y")
        di = tk.Frame(drm_f, bg=BG_CARD, padx=14, pady=12)
        di.pack(side="left", fill="x", expand=True)

        hr = tk.Frame(di, bg=BG_CARD)
        hr.pack(anchor="w")
        tk.Label(hr, text=drm["icon"], font=("Segoe UI Emoji", 18),
                 bg=BG_CARD).pack(side="left", padx=(0, 8))
        tk.Label(hr, text=drm["label"], font=("Segoe UI", 13, "bold"),
                 bg=BG_CARD, fg=drm["color"]).pack(side="left")
        tk.Label(di, text=drm["desc"], font=("Segoe UI", 9), bg=BG_CARD,
                 fg=TEXT_SEC, wraplength=420, justify="left",
                 anchor="w").pack(anchor="w", pady=(6, 0))

        if drm.get("always_online"):
            ao = tk.Frame(di, bg=BG_CARD)
            ao.pack(anchor="w", pady=(4, 0))
            tk.Label(ao, text="🌐", font=("Segoe UI Emoji", 12),
                     bg=BG_CARD).pack(side="left")
            tk.Label(ao, text="Always Online – requires persistent internet connection",
                     font=("Segoe UI", 9), bg=BG_CARD,
                     fg=COL_ALWAYS_ONLINE).pack(side="left", padx=(5, 0))

        if drm.get("anticheat"):
            ac = tk.Frame(di, bg=BG_CARD)
            ac.pack(anchor="w", pady=(4, 0))
            tk.Label(ac, text="🛡️", font=("Segoe UI Emoji", 12),
                     bg=BG_CARD).pack(side="left")
            tk.Label(ac, text=f"Anti-Cheat: {drm['anticheat']}",
                     font=("Segoe UI", 9), bg=BG_CARD,
                     fg=COL_ANTICHEAT).pack(side="left", padx=(5, 0))

        if drm.get("extras"):
            er = tk.Frame(di, bg=BG_CARD)
            er.pack(anchor="w", pady=(6, 0))
            tk.Label(er, text="Also:", font=("Segoe UI", 8),
                     bg=BG_CARD, fg=TEXT_MUTED).pack(side="left", padx=(0, 6))
            for extra in drm["extras"]:
                tk.Label(er, text=f" {extra} ", font=("Segoe UI", 8, "bold"),
                         bg=blend("#ffb74d"), fg="#ffb74d",
                         pady=1).pack(side="left", padx=(0, 4))

        pcgw_btn = tk.Label(di, text="  View on PCGamingWiki  ↗",
                            font=("Segoe UI", 8),
                            bg=blend(ACCENT, alpha=0.08), fg=ACCENT,
                            cursor="hand2", pady=5)
        pcgw_btn.pack(anchor="w", pady=(8, 0), fill="x")
        pcgw_url = f"https://www.pcgamingwiki.com/api/appid.php?appid={game['appid']}"
        pcgw_btn.bind("<Button-1>", lambda e, u=pcgw_url: __import__("webbrowser").open(u))
        pcgw_btn.bind("<Enter>", lambda e: pcgw_btn.configure(bg=blend(ACCENT, alpha=0.18)))
        pcgw_btn.bind("<Leave>", lambda e: pcgw_btn.configure(bg=blend(ACCENT, alpha=0.08)))

        BYPASS_SITES = [
            ("cs.rin.ru",                        "https://cs.rin.ru/forum/"),
            ("openlua.cloud",                    "https://openlua.cloud/"),
            ("GameCopyWorld.com",                "https://gamecopyworld.com/"),
            ("online-fix.me (if online co-op)",  "https://online-fix.me/"),
        ]

        def _bypass_row(parent, label):
            f = tk.Frame(parent, bg=BG_CARD)
            f.pack(anchor="w", pady=(4, 0))
            tk.Label(f, text=label, font=("Segoe UI", 8),
                     bg=BG_CARD, fg=TEXT_MUTED).pack(side="left")
            for i, (bname, u) in enumerate(BYPASS_SITES):
                lnk = tk.Label(f, text=bname, font=("Segoe UI", 8, "underline"),
                               fg=ACCENT, cursor="hand2", bg=BG_CARD)
                lnk.pack(side="left")
                lnk.bind("<Button-1>", lambda e, url=u: __import__("webbrowser").open(url))
                lnk.bind("<Enter>", lambda e, l=lnk: l.configure(fg=ACCENT_DIM))
                lnk.bind("<Leave>", lambda e, l=lnk: l.configure(fg=ACCENT))
                if i < len(BYPASS_SITES) - 1:
                    tk.Label(f, text="  •  ", font=("Segoe UI", 8),
                             bg=BG_CARD, fg=TEXT_MUTED).pack(side="left")

        extra_frame = tk.Frame(di, bg=BG_CARD)
        extra_frame.pack(fill="x", pady=(8, 0))

        if drm["type"] == "steamworks":
            tk.Label(extra_frame, text="✓ should work with SteamTools out of the box",
                     font=("Segoe UI", 9), bg=BG_CARD, fg=TEXT_PRI,
                     anchor="w").pack(anchor="w")
            gbe = tk.Button(extra_frame, text="Download GBE (for No-License errors)",
                            font=("Segoe UI", 9, "bold"), bg=ACCENT_DIM, fg=ACCENT,
                            cursor="hand2", relief="flat", padx=10, pady=5,
                            command=lambda: __import__("webbrowser").open(
                                "https://gitlab.com/Mr_Goldberg/goldberg_emulator/"
                                "-/jobs/4247811310/artifacts/download"))
            gbe.pack(anchor="w", pady=(2, 0))
            gbe.bind("<Enter>", lambda e: gbe.configure(bg=blend(ACCENT, alpha=0.3)))
            gbe.bind("<Leave>", lambda e: gbe.configure(bg=ACCENT_DIM))
            _bypass_row(extra_frame, "Also look for bypasses on: ")
        elif drm["type"] == "denuvo":
            lnk = tk.Label(extra_frame, text="🔍 find bypasses here",
                           font=("Segoe UI", 9, "underline"),
                           bg=BG_CARD, fg=ACCENT, cursor="hand2", anchor="w")
            lnk.pack(anchor="w")
            lnk.bind("<Button-1>", lambda e: __import__("webbrowser").open(
                "https://cs.rin.ru/forum/search.php?author_id=885704&sr=posts"))
            lnk.bind("<Enter>", lambda e: lnk.configure(fg=ACCENT_DIM))
            lnk.bind("<Leave>", lambda e: lnk.configure(fg=ACCENT))
            _bypass_row(extra_frame, "Also look for bypasses on: ")
        elif drm["type"] == "none":
            tk.Label(extra_frame, text="ℹ️ No need for bypass here — it doesn't have a DRM!",
                     font=("Segoe UI", 9), bg=BG_CARD, fg=TEXT_PRI,
                     anchor="w").pack(anchor="w")
        else:
            _bypass_row(extra_frame, "Look for bypasses on: ")

        online_fix_result = [None]
        online_fix_url    = ONLINE_FIX_SITE["query_url"] + urllib.parse.quote(clean_name, safe="")
        promo_frame       = tk.Frame(di, bg=BG_CARD)
        promo_frame.pack(fill="x", pady=(10, 0))

        def update_promo():
            try:
                if not promo_frame.winfo_exists():
                    return
            except Exception:
                return
            if request_id != self._online_fix_request_id:
                return
            for w in promo_frame.winfo_children():
                w.destroy()
            if online_fix_result[0] == "found":
                btn = tk.Button(promo_frame, text="🎮 Online-fix found! Click to open",
                                font=("Segoe UI", 9, "bold"), bg=ACCENT_DIM, fg=ACCENT,
                                cursor="hand2", relief="flat", padx=10, pady=5,
                                command=lambda: self._open_download_site(online_fix_url))
                btn.pack(fill="x")
                btn.bind("<Enter>", lambda e: btn.configure(bg=blend(ACCENT, alpha=0.3)))
                btn.bind("<Leave>", lambda e: btn.configure(bg=ACCENT_DIM))
            elif online_fix_result[0] == "not_found":
                is_coop = info and any(
                    "co-op" in cat.get("description", "").lower()
                    for cat in info.get("categories", [])
                )
                if is_coop and drm["type"] == "steamworks":
                    uf = tk.Frame(promo_frame, bg=BG_CARD, relief="solid", bd=1,
                                  highlightbackground=BORDER, highlightthickness=1)
                    uf.pack(fill="x")
                    inner = tk.Frame(uf, bg=BG_CARD, padx=10, pady=8)
                    inner.pack(fill="x")
                    tk.Label(inner, text="🎮 Co-op title with no EOS?",
                             font=("Segoe UI", 9, "bold"), bg=BG_CARD,
                             fg=TEXT_PRI, anchor="w").pack(anchor="w")
                    tk.Label(inner,
                             text="You may be able to use uc-online2 to play with your friends "
                                  "(you all have to apply it, follow instructions)",
                             font=("Segoe UI", 8), bg=BG_CARD, fg=TEXT_SEC,
                             anchor="w", wraplength=400,
                             justify="left").pack(anchor="w", pady=(2, 4))
                    uco = tk.Label(inner,
                                   text="https://github.com/UnionCrax-Team/uc-online2",
                                   font=("Segoe UI", 8, "underline"), fg=ACCENT,
                                   cursor="hand2", bg=BG_CARD, anchor="w")
                    uco.pack(anchor="w")
                    uco.bind("<Button-1>", lambda e: __import__("webbrowser").open(
                        "https://github.com/UnionCrax-Team/uc-online2"))
                    uco.bind("<Enter>", lambda e: uco.configure(fg=ACCENT_DIM))
                    uco.bind("<Leave>", lambda e: uco.configure(fg=ACCENT))

        def check_online_fix_thread():
            result = scrape.check_online_fix(ONLINE_FIX_SITE, clean_name)
            online_fix_result[0] = result
            self.after(0, update_promo)

        threading.Thread(target=check_online_fix_thread, daemon=True).start()

        if info and info.get("short_description"):
            df = tk.Frame(c, bg=BG_CARD, padx=14, pady=10)
            df.pack(fill="x", pady=(0, 14))
            tk.Label(df, text=info["short_description"], font=("Segoe UI", 9),
                     bg=BG_CARD, fg=TEXT_SEC, wraplength=460,
                     justify="left", anchor="w").pack(anchor="w")

        meta = {}
        if info:
            meta["Developer"] = ", ".join(info.get("developers", [])) or "—"
            meta["Publisher"] = ", ".join(info.get("publishers", [])) or "—"
            meta["Released"]  = info.get("release_date", {}).get("date", "—") or "—"
            po = info.get("price_overview")
            meta["Price"]     = (po["final_formatted"] if po
                                 else ("Free" if info.get("is_free") else "—"))
            meta["Genres"]    = ", ".join(g["description"]
                                          for g in info.get("genres", [])) or "—"
            meta["Platforms"] = ", ".join(k.capitalize()
                                          for k, v in info.get("platforms", {}).items()
                                          if v) or "—"
            mc = info.get("metacritic", {})
            if mc.get("score"):
                meta["Metacritic"] = f"{mc['score']} / 100"
        else:
            meta["Note"] = "Store data unavailable"

        grid = tk.Frame(c, bg=BG_DARK)
        grid.pack(fill="x", pady=(0, 4))
        for i, (k, v) in enumerate(meta.items()):
            cell = tk.Frame(grid, bg=BG_CARD, padx=12, pady=8)
            cell.grid(row=i // 2, column=i % 2, sticky="nsew",
                      padx=(0, 6) if i % 2 == 0 else 0, pady=(0, 6))
            tk.Label(cell, text=k.upper(), font=("Segoe UI", 8, "bold"),
                     bg=BG_CARD, fg=TEXT_MUTED, anchor="w").pack(anchor="w")
            tk.Label(cell, text=v, font=("Segoe UI", 10), bg=BG_CARD,
                     fg=TEXT_PRI, anchor="w", wraplength=180,
                     justify="left").pack(anchor="w", pady=(2, 0))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        tk.Frame(c, bg=BORDER, height=1).pack(fill="x", pady=(16, 0))

        hdr_row = tk.Frame(c, bg=BG_DARK)
        hdr_row.pack(fill="x", pady=(10, 6))
        tk.Label(hdr_row, text="📥  Download Sources",
                 font=("Segoe UI", 11, "bold"),
                 bg=BG_DARK, fg=TEXT_PRI).pack(side="left")
        counter_var = tk.StringVar(value="checking…")
        tk.Label(hdr_row, textvariable=counter_var, font=("Segoe UI", 9),
                 bg=BG_DARK, fg=TEXT_MUTED).pack(side="left", padx=(10, 0))

        leg = tk.Frame(c, bg=BG_DARK)
        leg.pack(anchor="w", pady=(0, 10))
        for color, txt in ((COL_FOUND, "Found"), (COL_NOTFOUND, "Not found / N/A")):
            tk.Frame(leg, bg=color, width=8, height=8).pack(side="left", padx=(0, 4))
            tk.Label(leg, text=txt, font=("Segoe UI", 8),
                     bg=BG_DARK, fg=TEXT_MUTED).pack(side="left", padx=(0, 12))

        def _open_site(site):
            self._open_download_site(
                site["query_url"] + urllib.parse.quote(clean_name, safe=""))

        chip_grid = scrape.ChipGrid(c, DOWNLOAD_SITES, cols=3, on_click=_open_site)
        chip_grid.pack(fill="x")

        total_sites = len(DOWNLOAD_SITES)
        result_q    = _queue.Queue()
        counters    = {"found": 0, "done": 0}

        def check_one(site):
            try:
                result = scrape.check_site_for_game(site, clean_name)
            except Exception:
                result = "error"
            result_q.put((site["name"], result))

        def flush_results():
            if request_id != self._online_fix_request_id:
                return
            try:
                if not chip_grid.winfo_exists():
                    return
            except Exception:
                return
            changed = False
            while True:
                try:
                    site_name, result = result_q.get_nowait()
                except _queue.Empty:
                    break
                try:
                    chip_grid.set_result(site_name, result)
                except tk.TclError:
                    return
                if result == "found":
                    counters["found"] += 1
                counters["done"] += 1
                changed = True
            if changed:
                try:
                    counter_var.set(
                        f"{counters['found']} found  "
                        f"({counters['done']}/{total_sites} checked) "
                        f"- do click on them to double-check yourself!")
                except tk.TclError:
                    return
            if counters["done"] < total_sites:
                self.after(150, flush_results)

        executor = ThreadPoolExecutor(max_workers=min(20, len(DOWNLOAD_SITES)))
        for site in DOWNLOAD_SITES:
            executor.submit(check_one, site)
        executor.shutdown(wait=False)
        self.after(150, flush_results)

                                 
        tk.Frame(c, bg=BORDER, height=1).pack(fill="x", pady=(16, 0))
        apply_frame = tk.Frame(c, bg=BG_DARK)
        apply_frame.pack(fill="x", pady=(8, 0))

        header_frame = tk.Frame(apply_frame, bg=BG_DARK)
        header_frame.pack(fill="x", pady=(0, 4))
        tk.Label(header_frame, text="🔄 Manifests (Hubcap)",
                 font=("Segoe UI", 10, "bold"),
                 bg=BG_DARK, fg=TEXT_PRI).pack(side="left")
        self._stats_label = tk.Label(header_frame, text="",
                                     font=("Segoe UI", 8),
                                     bg=BG_DARK, fg=TEXT_MUTED)
        self._stats_label.pack(side="right")
        refresh_lbl = tk.Label(header_frame, text="↻",
                               font=("Segoe UI Symbol", 10),
                               bg=BG_DARK, fg=TEXT_MUTED, cursor="hand2")
        refresh_lbl.pack(side="right", padx=(4, 0))
        refresh_lbl.bind("<Button-1>", lambda e: self._update_hubcap_stats_display())

        self._apply_status = tk.StringVar(value="")
        status_lbl = tk.Label(apply_frame, textvariable=self._apply_status,
                              font=("Segoe UI", 9), bg=BG_DARK, fg=TEXT_MUTED)
        status_lbl.pack(anchor="w", pady=(0, 4))

        btn_row = tk.Frame(apply_frame, bg=BG_DARK)
        btn_row.pack(fill="x", pady=(0, 4))

        tool_frame = tk.Frame(btn_row, bg=BG_DARK)
        tool_frame.pack(side="left", padx=(0, 10))
        tk.Label(tool_frame, text="Tool:", font=("Segoe UI", 9),
                 bg=BG_DARK, fg=TEXT_MUTED).pack(side="left")
        option_menu = tk.OptionMenu(tool_frame, self.selected_tool,
                                    "Steamtools", "OpenSteamTools")
        option_menu.config(bg=BG_INPUT, fg=TEXT_PRI, relief="flat",
                           highlightthickness=0, bd=0, font=("Segoe UI", 9))
        option_menu.pack(side="left", padx=(5, 0))

        def apply_manifests():
            self.after(0, lambda: self._apply_status.set(
                "⏳ Downloading and extracting..."))
            msg = self._apply_manifest(game["appid"])

            def finish():
                self._apply_status.set(msg)
                if msg.startswith("✅"):
                    if messagebox.askyesno(
                        "Restart Steam",
                        "Manifests applied successfully.\n"
                        "Steam must be restarted for changes to take effect.\n"
                        "Restart now?"):
                        threading.Thread(target=self._restart_steam,
                                         daemon=True).start()
                    self._update_hubcap_stats_delay()
            self.after(0, finish)

        apply_btn = tk.Button(
            btn_row, text="Apply Manifests",
            command=lambda: threading.Thread(
                target=apply_manifests, daemon=True).start(),
            bg=ACCENT_DIM, fg=ACCENT, font=("Segoe UI", 9, "bold"),
            relief="flat", padx=15, pady=5, cursor="hand2")
        apply_btn.pack(side="left")
        apply_btn.bind("<Enter>", lambda e: apply_btn.configure(bg=blend(ACCENT, alpha=0.3)))
        apply_btn.bind("<Leave>", lambda e: apply_btn.configure(bg=ACCENT_DIM))

        dots_btn = tk.Label(btn_row, text="⋮", font=("Segoe UI", 14, "bold"),
                            bg=BG_DARK, fg=TEXT_MUTED, cursor="hand2", padx=6)
        dots_btn.pack(side="left", padx=(4, 0))
        dots_btn.bind("<Button-1>",
                      lambda e, w=dots_btn, a=game["appid"]: self._open_dots_menu(w, a))
        dots_btn.bind("<Enter>", lambda e: dots_btn.configure(fg=ACCENT))
        dots_btn.bind("<Leave>", lambda e: dots_btn.configure(fg=TEXT_MUTED))

        restart_btn = tk.Button(
            btn_row, text="Restart Steam",
            command=lambda: threading.Thread(
                target=self._restart_steam, daemon=True).start(),
            bg=BG_INPUT, fg=TEXT_PRI, font=("Segoe UI", 9),
            relief="flat", padx=12, pady=5, cursor="hand2")
        restart_btn.pack(side="left", padx=(8, 0))
        restart_btn.bind("<Enter>", lambda e: restart_btn.configure(bg=BG_HOVER))
        restart_btn.bind("<Leave>", lambda e: restart_btn.configure(bg=BG_INPUT))

        self._update_hubcap_stats_display()
        tk.Frame(c, bg=BORDER, height=1).pack(fill="x", pady=(16, 0))
        btn = tk.Label(c, text="  Open on Steam Store  ↗",
                       font=("Segoe UI", 10, "bold"),
                       bg=ACCENT_DIM, fg=ACCENT, cursor="hand2", pady=10)
        btn.pack(fill="x", pady=(10, 0))
        store_url = f"https://store.steampowered.com/app/{game['appid']}"
        btn.bind("<Button-1>", lambda e: __import__("webbrowser").open(store_url))
        btn.bind("<Enter>", lambda e: btn.configure(bg="#1e5c7a"))
        btn.bind("<Leave>", lambda e: btn.configure(bg=ACCENT_DIM))

        self._set_status(f"Showing: {name}  •  DRM: {drm['label']}")

                                                                               
    def _open_settings(self):
        import webbrowser
        dialog = tk.Toplevel(self)
        dialog.title("Settings")
        dialog.geometry("480x540")
        dialog.configure(bg=BG_CARD)
        dialog.transient(self)
        dialog.grab_set()

        main = tk.Frame(dialog, bg=BG_CARD, padx=20, pady=20)
        main.pack(fill="both", expand=True)

        tk.Label(main, text="Steam Folder", font=("Segoe UI", 12, "bold"),
                 bg=BG_CARD, fg=TEXT_PRI).pack(anchor="w", pady=(0, 6))
        path_row = tk.Frame(main, bg=BG_CARD)
        path_row.pack(fill="x", pady=(0, 14))
        path_entry = tk.Entry(path_row, font=("Segoe UI", 10),
                              bg=BG_INPUT, fg=TEXT_PRI, insertbackground=ACCENT,
                              relief="flat", highlightthickness=1,
                              highlightbackground=BORDER, highlightcolor=ACCENT, bd=4)
        path_entry.pack(side="left", fill="x", expand=True)
        path_entry.insert(0, self.steam_path or r"C:\Program Files (x86)\Steam")

        def browse():
            from tkinter import filedialog
            p = filedialog.askdirectory()
            if p:
                path_entry.delete(0, tk.END)
                path_entry.insert(0, p)
        tk.Button(path_row, text="Browse", command=browse,
                  bg=BG_INPUT, fg=TEXT_PRI, font=("Segoe UI", 9),
                  relief="flat", padx=10, pady=3,
                  cursor="hand2").pack(side="left", padx=(6, 0))

        tk.Label(main, text="Hubcap Manifest API Key",
                 font=("Segoe UI", 12, "bold"),
                 bg=BG_CARD, fg=TEXT_PRI).pack(anchor="w", pady=(0, 6))
        entry = tk.Entry(main, font=("Segoe UI", 10), bg=BG_INPUT, fg=TEXT_PRI,
                         insertbackground=ACCENT, relief="flat", highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=ACCENT, bd=4)
        entry.pack(fill="x", pady=(0, 10))
        entry.insert(0, self.hubcap_api_key)

                                                           
        tk.Frame(main, bg=BORDER, height=1).pack(fill="x", pady=(10, 12))

        ost_row = tk.Frame(main, bg=BG_CARD)
        ost_row.pack(fill="x", pady=(0, 12))

        ost_text = tk.Frame(ost_row, bg=BG_CARD)
        ost_text.pack(side="left", fill="x", expand=True)
        tk.Label(ost_text, text="Disable OpenSteamTool",
                 font=("Segoe UI", 11, "bold"),
                 bg=BG_CARD, fg=TEXT_PRI).pack(anchor="w")
        tk.Label(ost_text,
                 text="Renames OpenSteamTool.dll to .disabled so Steam won't load it.",
                 font=("Segoe UI", 8),
                 bg=BG_CARD, fg=TEXT_MUTED,
                 wraplength=310, justify="left").pack(anchor="w", pady=(2, 0))

        self._disable_ost_var = tk.BooleanVar(
            value=ost.ost_currently_disabled(self.steam_path))

        def _toggle_ost():
            want = self._disable_ost_var.get()
            curr = ost.ost_currently_disabled(self.steam_path)
            if want == curr:
                return
            if want:
                if not messagebox.askyesno(
                    "Disable OpenSteamTool",
                    "This will rename OpenSteamTool.dll to .disabled.\n\n"
                    "Steam will not load OST until you turn this off again.\n"
                    "You will need to restart Steam for the change to take effect.\n\n"
                    "Continue?"
                ):
                    self._disable_ost_var.set(False)
                    self._ost_toggle.set_state(False)
                    return
                ok = ost.ost_set_disabled(self.steam_path, True)
                if ok:
                    self._set_status("🛑 OpenSteamTool disabled — restart Steam for it to take effect")
                else:
                    self._disable_ost_var.set(False)
                    self._ost_toggle.set_state(False)
                    messagebox.showerror("Disable OST",
                                         "Couldn't find OpenSteamTool.dll to disable.")
            else:
                ok = ost.ost_set_disabled(self.steam_path, False)
                if ok:
                    self._set_status("✅ OpenSteamTool re-enabled — restart Steam for it to take effect")
                else:
                    self._disable_ost_var.set(True)
                    self._ost_toggle.set_state(True)
                    messagebox.showerror("Enable OST",
                                         "Couldn't find OpenSteamTool.dll.disabled to restore.")

        self._ost_toggle = ToggleSwitch(ost_row, width=48, height=26,
                                        bg=BG_CARD,
                                        on_color=TOGGLE_ON, off_color=TOGGLE_OFF,
                                        variable=self._disable_ost_var,
                                        command=_toggle_ost)
        self._ost_toggle.pack(side="right", padx=(8, 0))

        tk.Frame(main, bg=BORDER, height=1).pack(fill="x", pady=(4, 12))

        btn_frame = tk.Frame(main, bg=BG_CARD)
        btn_frame.pack(fill="x", pady=(0, 10))

        def save_all():
            new_key  = entry.get().strip()
            new_path = path_entry.get().strip()
            if new_key:
                save_hubcap_key(new_key)
                self.hubcap_api_key = new_key
            if new_path and os.path.exists(new_path):
                save_steam_path(new_path)
                self.steam_path = new_path
            messagebox.showinfo("Saved", "Settings saved.")

        def check_usage():
            stats = api.get_hubcap_stats(self.hubcap_api_key)
            if isinstance(stats, dict):
                msg = (f"User: {stats.get('username', 'N/A')}\n"
                       f"Daily usage: {stats.get('daily_usage', 0)} / "
                       f"{stats.get('daily_limit', '?')}\n"
                       f"Total requests: {stats.get('api_key_usage_count', 0)}\n"
                       f"Key expires: {stats.get('api_key_expires_at', 'Never')}\n"
                       f"Requests allowed: "
                       f"{'Yes' if stats.get('can_make_requests') else 'No'}")
                messagebox.showinfo("Usage Statistics", msg)
            else:
                messagebox.showerror("Error", f"Failed to fetch stats:\n{stats}")

        tk.Button(btn_frame, text="Save", command=save_all,
                  bg=ACCENT, fg=BG_DARK, font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=15, pady=5,
                  cursor="hand2").pack(side="left", padx=(0, 10))
        tk.Button(btn_frame, text="Check Usage", command=check_usage,
                  bg=ACCENT_DIM, fg=ACCENT, font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=15, pady=5,
                  cursor="hand2").pack(side="left")

        link_frame = tk.Frame(main, bg=BG_CARD)
        link_frame.pack(anchor="w", pady=(10, 0))
        tk.Label(link_frame, text="Generate your key at: ",
                 font=("Segoe UI", 8), bg=BG_CARD, fg=TEXT_MUTED).pack(side="left")
        link_lbl = tk.Label(link_frame,
                            text="hubcapmanifest.com/api-keys/stats",
                            font=("Segoe UI", 8, "underline"),
                            fg=ACCENT, cursor="hand2", bg=BG_CARD)
        link_lbl.pack(side="left")
        link_lbl.bind("<Button-1>", lambda e: webbrowser.open(
            "https://hubcapmanifest.com/api-keys/stats"))
        link_lbl.bind("<Enter>", lambda e: link_lbl.configure(fg=ACCENT_DIM))
        link_lbl.bind("<Leave>", lambda e: link_lbl.configure(fg=ACCENT))

                                                                               
    def _open_library_scan(self, parent_window=None):
                                                                           
        from savegd_core import library as sg_library

        try:
            installed = sg_library.scan_installed_games(self.steam_path)
        except Exception as e:
            messagebox.showerror("Save Sync", f"Library scan failed:\n{e}")
            return

                                           
        enrolled = set(str(g["appid"]) for g in sg_manifest.all_games())
        candidates = [g for g in installed if str(g["appid"]) not in enrolled]

        if not candidates:
            messagebox.showinfo(
                "Save Sync",
                f"All {len(installed)} installed Steam games are already enrolled."
            )
            return

                                                                             
        win = tk.Toplevel(self)
        win.title("Add from Steam Library")
        win.geometry("720x560")
        win.configure(bg=BG_CARD)
        win.transient(parent_window or self)
        win.grab_set()

        main = tk.Frame(win, bg=BG_CARD, padx=16, pady=16)
        main.pack(fill="both", expand=True)

        tk.Label(main, text="Add Games from Steam Library",
                font=("Segoe UI", 13, "bold"),
                bg=BG_CARD, fg=TEXT_PRI).pack(anchor="w")
        tk.Label(main,
                text=f"Found {len(installed)} installed games. "
                    f"{len(candidates)} not yet enrolled.",
                font=("Segoe UI", 9),
                bg=BG_CARD, fg=TEXT_SEC).pack(anchor="w", pady=(2, 10))

                       
        search_var = tk.StringVar()
        tk.Entry(main, textvariable=search_var,
                font=("Segoe UI", 10),
                bg=BG_INPUT, fg=TEXT_PRI,
                insertbackground=ACCENT,
                relief="flat", highlightthickness=1,
                highlightbackground=BORDER, highlightcolor=ACCENT,
                bd=4).pack(fill="x", pady=(0, 8))

                 
        list_frame = tk.Frame(main, bg=BG_CARD)
        list_frame.pack(fill="both", expand=True)

        sb = tk.Scrollbar(list_frame, orient="vertical")
        sb.pack(side="right", fill="y")

        lb = tk.Listbox(list_frame,
                        selectmode="extended",
                        bg=BG_INPUT, fg=TEXT_PRI,
                        selectbackground=ACCENT_DIM,
                        selectforeground=ACCENT,
                        font=("Segoe UI", 10),
                        relief="flat", highlightthickness=0,
                        yscrollcommand=sb.set)
        lb.pack(side="left", fill="both", expand=True)
        sb.config(command=lb.yview)

        displayed = []

        def refresh(*_):
            lb.delete(0, tk.END)
            displayed.clear()
            q = search_var.get().lower()
            for g in candidates:
                if q and q not in g["name"].lower() and q not in str(g["appid"]):
                    continue
                displayed.append(g)
                lb.insert(tk.END, f"{g['name']}  ({g['appid']})")

        search_var.trace_add("write", refresh)
        refresh()

                                                                              
        btn_row = tk.Frame(main, bg=BG_CARD)
        btn_row.pack(fill="x", pady=(10, 0))

        def add_selected():
            sel = lb.curselection()
            if not sel:
                messagebox.showinfo("Save Sync", "Select one or more games first.")
                return

            added = 0
            needs_path = []
            failed = []

            for i in sel:
                g = displayed[i]
                try:
                    entry = sg_manifest.enroll_and_resolve(
                        g["appid"], g["name"], self.steam_path)
                    added += 1
                    if not entry or not entry.get("save_path"):
                        needs_path.append(g["name"])
                except Exception as e:
                    failed.append(f"{g['name']}: {e}")

            summary = f"Added {added} games to Save Sync."
            if needs_path:
                preview = "\n".join(needs_path[:5])
                if len(needs_path) > 5:
                    preview += f"\n... and {len(needs_path) - 5} more"
                summary += (f"\n\nNo save path found for:\n{preview}\n\n"
                            f"Use 'Set Path' on those cards.")
            if failed:
                summary += "\n\nFailed:\n" + "\n".join(failed[:3])

            messagebox.showinfo("Save Sync", summary)
            win.destroy()

                                                 
            if parent_window is not None:
                try:
                    parent_window.destroy()
                except Exception:
                    pass
                self._open_save_sync()

        def select_all():
            lb.selection_set(0, tk.END)

        tk.Button(btn_row, text="Add Selected",
                command=add_selected,
                bg=ACCENT_DIM, fg=ACCENT,
                font=("Segoe UI", 9, "bold"),
                relief="flat", padx=14, pady=5,
                cursor="hand2").pack(side="left")

        tk.Button(btn_row, text="Select All",
                command=select_all,
                bg=BG_INPUT, fg=TEXT_PRI,
                font=("Segoe UI", 9),
                relief="flat", padx=14, pady=5,
                cursor="hand2").pack(side="left", padx=(6, 0))

        tk.Button(btn_row, text="Cancel",
                command=win.destroy,
                bg=BG_INPUT, fg=TEXT_SEC,
                font=("Segoe UI", 9),
                relief="flat", padx=14, pady=5,
                cursor="hand2").pack(side="right")


    def _open_save_sync(self):
                                                                   
        ok, msg = sg_paths.ensure_runtime_ready()
        if not ok:
            messagebox.showerror("Save Sync Setup", msg)
            return

        win = tk.Toplevel(self)
        win.title("Save Sync")
        win.geometry("900x620")
        win.configure(bg=BG_DARK)
        win.transient(self)
        win.grab_set()

                                                                           
        hdr = tk.Frame(win, bg=BG_MID, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="💾  Save Sync",
                font=("Segoe UI", 14, "bold"),
                bg=BG_MID, fg=ACCENT).pack(side="left", padx=16)

        token_ok = sg_paths.token_file().exists()
        status_text  = "☁ Authorized" if token_ok else "⚠ Not authorized"
        status_color = ACCENT if token_ok else "#ef5350"

        tk.Label(hdr, text=status_text,
                font=("Segoe UI", 9, "bold"),
                bg=BG_MID, fg=status_color).pack(side="right", padx=16)

        if not token_ok:
            tk.Button(hdr, text="Authorize Google Drive",
                    command=self._run_save_gd_setup,
                    bg=ACCENT_DIM, fg=ACCENT,
                    font=("Segoe UI", 9, "bold"),
                    relief="flat", padx=12, pady=4,
                    cursor="hand2").pack(side="right", padx=(0, 8))
                                       
        tk.Button(hdr, text="📚  Scan Library",
                command=lambda: self._open_library_scan(win),
                bg=BG_INPUT, fg=TEXT_PRI,
                font=("Segoe UI", 9),
                relief="flat", padx=12, pady=4,
                cursor="hand2").pack(side="right", padx=(0, 8))
                                                                           
        scroll_container = tk.Frame(win, bg=BG_DARK)
        scroll_container.pack(fill="both", expand=True, padx=16, pady=12)

        canvas = tk.Canvas(scroll_container, bg=BG_DARK, highlightthickness=0)
        sb     = tk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview)
        inner  = tk.Frame(canvas, bg=BG_DARK)

        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        inner.bind("<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        games = sg_manifest.all_games()
        if not games:
            tk.Label(inner,
                    text="No games enrolled.\n\n"
                        "Search for a game, click the ⋮ menu on its row,\n"
                        "and choose 'Add to Save Sync'.",
                    font=("Segoe UI", 11), bg=BG_DARK, fg=TEXT_MUTED,
                    justify="center").pack(expand=True, pady=80)
        else:
            for g in games:
                self._make_save_sync_card(inner, g)

                                                                           
        footer = tk.Frame(win, bg=BG_MID, height=42)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        tk.Button(footer, text="Close", command=win.destroy,
                bg=BG_INPUT, fg=TEXT_SEC, font=("Segoe UI", 9),
                relief="flat", padx=14, pady=4,
                cursor="hand2").pack(side="right", padx=12, pady=6)


    def _make_save_sync_card(self, parent, game):
                                                    
        card = tk.Frame(parent, bg=BG_CARD, padx=12, pady=10)
        card.pack(fill="x", pady=(0, 8))

                         
        info = tk.Frame(card, bg=BG_CARD)
        info.pack(side="left", fill="x", expand=True)

        tk.Label(info, text=game.get("name", f"AppID {game['appid']}"),
                font=("Segoe UI", 11, "bold"),
                bg=BG_CARD, fg=TEXT_PRI,
                anchor="w").pack(anchor="w")

        sp  = game.get("save_path", "")
        src = game.get("save_path_source", "") or "unknown"

        if sp:
            tk.Label(info, text=f"📁 {sp}",
                    font=("Segoe UI", 8), bg=BG_CARD, fg=TEXT_MUTED,
                    anchor="w", wraplength=550,
                    justify="left").pack(anchor="w", pady=(2, 0))
            tk.Label(info, text=f"Source: {src}",
                    font=("Segoe UI", 7), bg=BG_CARD, fg=TEXT_MUTED,
                    anchor="w").pack(anchor="w")
        else:
            tk.Label(info, text="⚠ Save path not set — click 'Set Path'",
                    font=("Segoe UI", 8), bg=BG_CARD, fg="#ffb74d",
                    anchor="w").pack(anchor="w", pady=(2, 0))

        last_sync = game.get("last_sync")
        if last_sync:
            try:
                from datetime import datetime
                ts = datetime.fromtimestamp(last_sync).strftime("%d %b %Y %H:%M")
                tk.Label(info, text=f"Last sync: {ts}",
                        font=("Segoe UI", 7), bg=BG_CARD, fg=TEXT_MUTED,
                        anchor="w").pack(anchor="w")
            except Exception:
                pass

                              
        ctrl = tk.Frame(card, bg=BG_CARD)
        ctrl.pack(side="right")

        auto_var = tk.BooleanVar(value=game.get("auto_download", False))

        def toggle_auto():
            sg_manifest.update_game(game["appid"], auto_download=auto_var.get())

        tk.Checkbutton(ctrl, text="Auto-download",
                    variable=auto_var,
                    command=toggle_auto,
                    bg=BG_CARD, fg=TEXT_PRI,
                    selectcolor=BG_CARD,
                    activebackground=BG_CARD,
                    activeforeground=ACCENT,
                    font=("Segoe UI", 8)).pack(side="left", padx=(0, 8))

        if not sp:
            tk.Button(ctrl, text="Set Path",
                    command=lambda g=game: self._set_save_path(g["appid"]),
                    bg=ACCENT_DIM, fg=ACCENT,
                    font=("Segoe UI", 8, "bold"),
                    relief="flat", padx=8, pady=3,
                    cursor="hand2").pack(side="left", padx=(0, 4))

        tk.Button(ctrl, text="Sync Now",
                command=lambda g=game: self._sync_save_now(g["appid"]),
                bg=BG_INPUT, fg=TEXT_PRI,
                font=("Segoe UI", 8),
                relief="flat", padx=8, pady=3,
                cursor="hand2").pack(side="left", padx=(0, 4))

        tk.Button(ctrl, text="Remove",
                command=lambda g=game: self._unenroll_save_sync(g["appid"], card),
                bg=BG_INPUT, fg=TEXT_MUTED,
                font=("Segoe UI", 8),
                relief="flat", padx=8, pady=3,
                cursor="hand2").pack(side="left")


    def _set_save_path(self, appid):
                                                                    
        from tkinter import filedialog
        folder = filedialog.askdirectory(title="Select the game's save folder")
        if not folder:
            return
        sg_manifest.set_manual_path(appid, folder, self.steam_path)           
        messagebox.showinfo("Save Sync", f"Save path set for AppID {appid}.")


    def _sync_save_now(self, appid):
                                                 
        entry = sg_manifest.get_game(appid)
        if not entry or not entry.get("save_path"):
            messagebox.showerror("Save Sync", "No save path set for this game.")
            return

        if not sg_paths.token_file().exists():
            messagebox.showerror("Save Sync",
                                "Not authorized. Click 'Authorize Google Drive' first.")
            return

        def worker():
            client = sg_sync.DriveClient(str(sg_paths.token_file()))
            if not client.authenticate():
                self.after(0, lambda: messagebox.showerror(
                    "Save Sync", "Token invalid. Re-authorize."))
                return
            try:
                result = sg_sync.sync_game(
                    appid, entry["save_path"], client,
                    entry.get("auto_download", False))
                import time as _t
                sg_manifest.update_game(
                    appid,
                    last_sync=_t.time(),
                    last_upload=_t.time() if result["action"] == "uploaded" else entry.get("last_upload"),
                    last_download=_t.time() if result["action"] == "downloaded" else entry.get("last_download"),
                )
                self.after(0, lambda: messagebox.showinfo(
                    "Save Sync", f"{result['action']}: {result['message']}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror(
                    "Save Sync", f"Sync failed:\n{e}"))

        threading.Thread(target=worker, daemon=True).start()


    def _unenroll_save_sync(self, appid, card_widget):
                                           
        if not messagebox.askyesno("Remove Game",
                                "Remove this game from Save Sync?\n\n"
                                "It won't delete anything on Drive or on disk."):
            return
        sg_manifest.unenroll_game(appid)
        card_widget.destroy()


    def _run_save_gd_setup(self):
                                                                         
        exe = Path(_ASSETS_DIR) / "save_gd.exe"
        if not exe.exists():
            messagebox.showerror(
                "Save Sync",
                f"save_gd.exe not found at:\n{exe}\n\n"
                "Copy it from steam_lookup_assets/ first, or build it with "
                "save_gd/build.bat.")
            return
        subprocess.Popen([str(exe), "--setup"], cwd=str(exe.parent))
        messagebox.showinfo(
            "Save Sync",
            "Browser will open for Google sign-in.\n\n"
            "Complete the flow, then reopen this window.")


    def _open_cloudredirect_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("CloudRedirect")
        dialog.geometry("520x340")
        dialog.configure(bg=BG_CARD)
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        main = tk.Frame(dialog, bg=BG_CARD, padx=22, pady=20)
        main.pack(fill="both", expand=True)

                      
        tk.Label(
            main,
            text="CloudRedirect",
            font=("Segoe UI", 14, "bold"),
            bg=BG_CARD,
            fg=ACCENT,
        ).pack(anchor="w")

        tk.Label(
            main,
            text=(
                "One-click setup.\n\n"
                "• Copies cloud_redirect.dll into your Steam root\n"
                "• Restarts Steam so the DLL loads\n"
                "• Launches CloudRedirect.exe detached\n\n"
                f"Files required in:\n{ASSETS_DIR}"
            ),
            font=("Segoe UI", 9),
            bg=BG_CARD,
            fg=TEXT_SEC,
            justify="left",
            wraplength=470,
        ).pack(anchor="w", pady=(7, 18))

                      
        status_frame = tk.Frame(main, bg=BG_CARD)
        status_frame.pack(fill="x", pady=(0, 16))

        status_lbl = tk.Text(
            status_frame,
            height=4,
            wrap="word",
            font=("Segoe UI", 9),
            bg=BG_CARD,
            fg=TEXT_MUTED,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            state="disabled",
            cursor="arrow",
        )
        status_lbl.pack(side="left", fill="both", expand=True)

        status_scrollbar = tk.Scrollbar(
            status_frame,
            orient="vertical",
            command=status_lbl.yview,
            bg=BG_CARD,
            troughcolor=BG_CARD,
            activebackground=TEXT_MUTED,
            highlightthickness=0,
            bd=0,
            width=8,
        )
        status_scrollbar.pack(side="right", fill="y")

        status_lbl.configure(yscrollcommand=status_scrollbar.set)

        def show_status(text, color=TEXT_MUTED):
            status_lbl.configure(state="normal")
            status_lbl.delete("1.0", "end")
            status_lbl.insert("1.0", text)
            status_lbl.configure(
                state="disabled",
                fg=color,
            )
            status_lbl.yview_moveto(0)

        def set_status(text, color=TEXT_MUTED):
            self.after(
                0,
                lambda: show_status(text, color),
            )

                     
        def do_setup():
            setup_btn.configure(
                state="disabled",
                text="Working…",
                bg=ACCENT_DIM,
                disabledforeground=ACCENT,
                cursor="arrow",
            )

            def worker():
                ok, msg = steam_ops.setup_cloud_redirect(
                    self.steam_path,
                    on_status=lambda t, c=None: set_status(
                        t,
                        c or TEXT_MUTED,
                    ),
                )

                def finish():
                    show_status(
                        msg,
                        ACCENT if ok else "#ef5350",
                    )

                    if ok:
                        setup_btn.configure(
                            state="normal",
                            text="Done",
                            bg=ACCENT_DIM,
                            fg=ACCENT,
                            cursor="hand2",
                            command=dialog.destroy,
                        )
                    else:
                        setup_btn.configure(
                            state="normal",
                            text="Retry",
                            bg=ACCENT_DIM,
                            fg=ACCENT,
                            cursor="hand2",
                            command=do_setup,
                        )

                self.after(0, finish)

            threading.Thread(
                target=worker,
                daemon=True,
            ).start()

                              
        setup_btn = tk.Button(
            main,
            text="Install & Run CloudRedirect",
            command=do_setup,
            bg=ACCENT_DIM,
            fg=ACCENT,
            activebackground=blend(ACCENT, alpha=0.3),
            activeforeground=ACCENT,
            disabledforeground=ACCENT,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=18,
            pady=8,
            cursor="hand2",
        )
        setup_btn.pack(
            anchor="w",
            padx=0,
            pady=(0, 18),
        )

                                
        tk.Frame(
            main,
            bg=BORDER,
            height=1,
        ).pack(fill="x", pady=(0, 10))

                               
        bottom = tk.Frame(main, bg=BG_CARD)
        bottom.pack(fill="x")

        tk.Button(
            bottom,
            text="Close",
            command=dialog.destroy,
            bg=BG_INPUT,
            fg=TEXT_SEC,
            activebackground=BG_HOVER,
            activeforeground=TEXT_PRI,
            font=("Segoe UI", 9),
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=14,
            pady=5,
            cursor="hand2",
        ).pack(side="right")



                                                                               
    def _update_hubcap_stats_display(self):
        if not self._stats_label:
            return
        label = self._stats_label
        try:
            label.config(text="Checking...")
        except tk.TclError:
            return

        def safe_set(text):
            try: label.config(text=text)
            except tk.TclError: pass

        def worker():
            stats = api.get_hubcap_stats(self.hubcap_api_key)
            if isinstance(stats, dict):
                usage = stats.get('daily_usage', '?')
                limit = stats.get('daily_limit', '?')
                text  = f"Usage: {usage}/{limit} today"
                expires = stats.get('api_key_expires_at')
                if expires:
                    try:
                        exp_date  = datetime.fromisoformat(expires.replace('Z', '+00:00'))
                        days_left = (exp_date - datetime.now(exp_date.tzinfo)).days
                        if days_left < 7:
                            text += f"  (expires in {days_left}d)"
                    except Exception:
                        pass
                self.after(0, lambda: safe_set(text))
            else:
                self.after(0, lambda: safe_set("Stats unavailable"))
        threading.Thread(target=worker, daemon=True).start()

    def _update_hubcap_stats_delay(self):
        self.after(1000, self._update_hubcap_stats_display)

                                                                               
    def _restart_steam(self):
        msg = steam_ops.restart_steam(self.steam_path)
        self.after(0, lambda: messagebox.showinfo("Restart Steam", msg))

    def _apply_manifest(self, appid: int, tool: str = None) -> str:
        if tool is None:
            tool = self.selected_tool.get()
        if not self.hubcap_api_key:
            return "❌ Hubcap API key not set. Go to Settings (⚙) to add it."

        steam_root = Path(self.steam_path or r"C:\Program Files (x86)\Steam")
        depotcache = steam_root / "depotcache"
        lua_dir    = (steam_root / "config" / "stplug-in" if tool == "Steamtools"
                      else steam_root / "config" / "lua")
        depotcache.mkdir(parents=True, exist_ok=True)
        lua_dir.mkdir(parents=True, exist_ok=True)

        zip_path = Path.home() / f"manifest_{appid}.zip"
        url = f"https://hubcapmanifest.com/api/v1/manifest/{appid}"
        headers = {"Authorization": f"Bearer {self.hubcap_api_key}"}
        requests = lazy.get_requests()
        try:
            resp = requests.get(url, headers=headers, stream=True, timeout=30)
            if resp.status_code != 200:
                return f"❌ API error: {resp.status_code} – {resp.text[:200]}"
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
        except Exception as e:
            return f"❌ Download failed: {e}"

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for info in zf.infolist():
                    zf.extract(info, zip_path.parent / "temp_manifest")
                temp_dir = zip_path.parent / "temp_manifest"
                for file in temp_dir.rglob("*"):
                    if file.is_file():
                        if file.suffix == ".manifest":
                            shutil.copy(file, depotcache / file.name)
                        elif file.suffix == ".lua":
                            shutil.copy(file, lua_dir / file.name)
                shutil.rmtree(temp_dir)
            zip_path.unlink()
            return f"✅ Manifests applied successfully for {tool}!"
        except Exception as e:
            return f"❌ Extraction failed: {e}"

                                                                               
    def _open_game_remover_dialog(self, appid: int = None):
        dialog = tk.Toplevel(self)
        dialog.title("Remove Game Files")
        dialog.geometry("680x560")
        dialog.configure(bg=BG_CARD)
        dialog.transient(self)
        dialog.grab_set()

        main = tk.Frame(dialog, bg=BG_CARD, padx=16, pady=16)
        main.pack(fill="both", expand=True)

        tk.Label(main, text="Remove Game",
                 font=("Segoe UI", 13, "bold"), bg=BG_CARD, fg=TEXT_PRI).pack(anchor="w")
        tk.Label(main,
                 text="Deletes matching .st / .manifest / .bin / stats files for the given AppID\n"
                      "from your Steam folder (stplug-in, depotcache, depotcache/config, "
                      "stUI, StatsExport, lua).",
                 font=("Segoe UI", 9), bg=BG_CARD, fg=TEXT_SEC,
                 justify="left").pack(anchor="w", pady=(2, 10))

        row = tk.Frame(main, bg=BG_CARD)
        row.pack(fill="x", pady=(0, 8))
        tk.Label(row, text="AppID:", font=("Segoe UI", 10),
                 bg=BG_CARD, fg=TEXT_PRI).pack(side="left")
        id_var = tk.StringVar(value=str(appid) if appid else "")
        tk.Entry(row, textvariable=id_var, font=("Segoe UI", 10),
                 bg=BG_INPUT, fg=TEXT_PRI, insertbackground=ACCENT,
                 relief="flat", highlightthickness=1,
                 highlightbackground=BORDER, highlightcolor=ACCENT,
                 bd=4).pack(side="left", fill="x", expand=True, padx=(8, 0))

        log_frame = tk.Frame(main, bg=BG_CARD)
        log_frame.pack(fill="both", expand=True, pady=(8, 0))
        sb = tk.Scrollbar(log_frame, orient="vertical")
        sb.pack(side="right", fill="y")
        log_box = tk.Text(log_frame, bg=BG_INPUT, fg=TEXT_PRI,
                          font=("Consolas", 9), relief="flat",
                          highlightthickness=0, wrap="word",
                          yscrollcommand=sb.set)
        log_box.pack(side="left", fill="both", expand=True)
        sb.config(command=log_box.yview)
        log_box.tag_config("red",    foreground="#ef5350")
        log_box.tag_config("green",  foreground="#81c784")
        log_box.tag_config("yellow", foreground="#ffb74d")
        log_box.tag_config("cyan",   foreground="#4fc3f7")

        def log_fn(text, color="white"):
            try:
                log_box.insert(tk.END, text, color)
                log_box.see(tk.END)
            except tk.TclError:
                pass

        def do_remove():
            s = id_var.get().strip()
            if not s.isdigit():
                log_fn("❌ Invalid AppID.\n", "red")
                return
            log_fn(f"AppID: {s}\nDeleting files:\n", "yellow")
            n = steam_ops.remove_game_files(self.steam_path, int(s), log_fn)
            if n > 0:
                log_fn(f"\n✅ Deleted {n} file(s).\n", "green")
            else:
                log_fn(f"\n⚠️ No files found for AppID {s}.\n", "yellow")

        btn_row = tk.Frame(main, bg=BG_CARD)
        btn_row.pack(fill="x", pady=(8, 0))
        tk.Button(btn_row, text="Remove Files", command=do_remove,
                  bg="#dc2626", fg="#ffffff", font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=15, pady=5,
                  cursor="hand2").pack(side="left")
        tk.Button(btn_row, text="Close", command=dialog.destroy,
                  bg=BG_INPUT, fg=TEXT_SEC, font=("Segoe UI", 9),
                  relief="flat", padx=15, pady=5,
                  cursor="hand2").pack(side="right")

                                                                               
    def _open_dots_menu(self, anchor_widget, appid: int):
        menu = tk.Menu(self, tearoff=0, bg=BG_CARD, fg=TEXT_PRI,
                    activebackground=ACCENT_DIM, activeforeground=ACCENT,
                    bd=0, relief="flat", font=("Segoe UI", 9))
        menu.add_command(label="Deploy OST bypass to game folder…",
                        command=self._deploy_ost_bypass)
        menu.add_command(label="Remove OST bypass from folder…",
                        command=self._remove_ost_bypass)
        menu.add_separator()
        menu.add_command(label="Add to Save Sync…",
                        command=lambda: self._enroll_save_sync(appid))
        menu.add_separator()
        menu.add_command(label="Remove Game Files…",
                        command=lambda: self._open_game_remover_dialog(appid))
        try:
            x = anchor_widget.winfo_rootx()
            y = anchor_widget.winfo_rooty() + anchor_widget.winfo_height()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()
    
    def _enroll_save_sync(self, appid):
                                                                                  
        from tkinter import filedialog

                                 
        folder = filedialog.askdirectory(
            title="Select the game's folder (where game.exe lives)")
        if not folder:
            return
        game_dir = Path(folder)

                      
        game_exe = steam_ops.find_game_exe(game_dir)
        if not game_exe:
            messagebox.showerror("Save Sync", f"No .exe found in {game_dir}")
            return

        name = game_exe.stem

                                              
        entry = sg_manifest.enroll_and_resolve(appid, name, self.steam_path)
        if not entry:
            messagebox.showerror("Save Sync", "Failed to enroll game.")
            return

                                               
        src_dll = Path(ASSETS_DIR) / "version.dll"
        dll_msg = ""
        if src_dll.exists():
            try:
                shutil.copy(src_dll, game_dir / "version.dll")
                dll_msg = "✅ version.dll deployed"
            except Exception as e:
                dll_msg = f"⚠ Couldn't copy version.dll: {e}"
        else:
            dll_msg = f"⚠ version.dll not found in {ASSETS_DIR}"

                               
        marker = game_dir / ".steam_lookup_save_gd.json"
        marker.write_text(json.dumps({
            "appid": appid,
            "name": name,
            "enrolled_at": time.time(),
        }, indent=2))

                                             
        dirs = entry.get("deployed_dirs", [])
        if str(game_dir) not in dirs:
            dirs.append(str(game_dir))
        sg_manifest.update_game(appid, deployed_dirs=dirs)

        path = entry.get("save_path", "")
        src  = entry.get("save_path_source", "")

        messagebox.showinfo(
            "Save Sync",
            f"Enrolled: {name}\n\n"
            f"Save path: {path or '(not set — click Set Path in Save Sync)'}\n"
            f"Source: {src or 'unknown'}\n\n"
            f"{dll_msg}\n\n"
            f"Game folder:\n{game_dir}"
        )
    def _deploy_ost_bypass(self, game_dir: Path = None):
        from tkinter import filedialog
        if game_dir is None:
            folder = filedialog.askdirectory(
                title="Select the game's folder (where the .exe lives)")
            if not folder:
                return
            game_dir = Path(folder)
        ok, msg = ost.deploy_bypass(game_dir)
        if ok:
            messagebox.showinfo("OST bypass deployed", msg)
        else:
            messagebox.showerror("Deploy failed", msg)

    def _remove_ost_bypass(self, game_dir: Path = None):
        from tkinter import filedialog
        if game_dir is None:
            folder = filedialog.askdirectory(title="Select the game's folder")
            if not folder:
                return
            game_dir = Path(folder)
        ok, msg = ost.remove_bypass(game_dir)
        if ok:
            messagebox.showinfo("Removed", msg)
        else:
            messagebox.showerror("Not deployed", msg)

                                                                               
    def _open_download_site(self, url):
        if self._reminder_disabled:
            __import__("webbrowser").open(url)
        else:
            self._show_reminder_dialog(url)

    def _show_reminder_dialog(self, url):
        dialog = tk.Toplevel(self)
        dialog.title("Reminder – Safe Browsing")
        dialog.geometry("500x300")
        dialog.configure(bg=BG_CARD)
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        frame = tk.Frame(dialog, bg=BG_CARD, padx=20, pady=20)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="⚠️ Before you continue",
                 font=("Segoe UI", 14, "bold"),
                 bg=BG_CARD, fg=ACCENT).pack(anchor="w", pady=(0, 10))
        tk.Label(frame,
                 text="We strongly recommend using Firefox with uBlock Origin\n"
                      "to block malicious ads and protect your privacy when\n"
                      "visiting these download sites.",
                 font=("Segoe UI", 10), bg=BG_CARD, fg=TEXT_PRI,
                 justify="left").pack(anchor="w", pady=(0, 10))

        link_frame = tk.Frame(frame, bg=BG_CARD)
        link_frame.pack(anchor="w", pady=(0, 15))
        for text, link_url in (
            ("Download Firefox", "https://www.firefox.com/en-GB/"),
            ("uBlock Origin add-on",
             "https://addons.mozilla.org/en-GB/firefox/addon/ublock-origin/"),
        ):
            lbl = tk.Label(link_frame, text=text,
                           font=("Segoe UI", 9, "underline"),
                           fg=ACCENT, cursor="hand2", bg=BG_CARD)
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e, u=link_url: __import__("webbrowser").open(u))
            lbl.bind("<Enter>", lambda e, l=lbl: l.configure(fg=ACCENT_DIM))
            lbl.bind("<Leave>", lambda e, l=lbl: l.configure(fg=ACCENT))
            if text == "Download Firefox":
                tk.Label(link_frame, text="  |  ", bg=BG_CARD,
                         fg=TEXT_MUTED).pack(side="left")

        var = tk.BooleanVar(value=False)
        tk.Checkbutton(frame, text="Don't show this reminder again",
                       variable=var, bg=BG_CARD, fg=TEXT_PRI,
                       selectcolor=BG_CARD, activebackground=BG_CARD,
                       font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 20))

        btn_frame = tk.Frame(frame, bg=BG_CARD)
        btn_frame.pack(fill="x")

        def open_and_close():
            if var.get():
                self._reminder_disabled = True
                save_reminder_state(True)
            dialog.destroy()
            __import__("webbrowser").open(url)

        tk.Button(btn_frame, text="Open Site", command=open_and_close,
                  bg=ACCENT, fg=BG_DARK, font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=15, pady=5,
                  cursor="hand2").pack(side="right")
        tk.Button(btn_frame, text="Cancel", command=dialog.destroy,
                  bg=BG_INPUT, fg=TEXT_SEC, font=("Segoe UI", 9),
                  relief="flat", padx=15, pady=5,
                  cursor="hand2").pack(side="right", padx=(0, 10))

                                                                               
    def _set_status(self, text: str):
        try: self._status.configure(text=text)
        except tk.TclError: pass

                                                                               
    def _on_close(self):
        try:
            self.destroy()
        except Exception:
            pass
        scrape.close_driver_pool()
        os.kill(os.getpid(), 9)