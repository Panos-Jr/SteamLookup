\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
   

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

                                                                                
_here = Path(__file__).resolve().parent
_root = _here.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from savegd_core import manifest as sg_manifest
from savegd_core import paths as sg_paths
from savegd_core import sync as sg_sync
from savegd_core import steam_local


                                                                                
BG_FIRST_TICK_MS = 5_000                                                  
BG_INTERVAL_MS   = 10 * 60 * 1000                           


                                                                                
BG_DARK    = "#0a0d14"
BG_MID     = "#0f1117"
BG_CARD    = "#13161f"
BG_INPUT   = "#1a1d28"
BG_HOVER   = "#1e2130"
BG_SEL     = "#162035"
ACCENT     = "#4fc3f7"
ACCENT_DIM = "#1b4f6b"
TEXT_PRI   = "#e8eaf6"
TEXT_SEC   = "#9ca3af"
TEXT_MUTED = "#4b5563"
BORDER     = "#1e2433"
WARN       = "#ffb74d"
DANGER     = "#ef5350"
OK         = "#81c784"


                                                                                
def _show_toast(title: str, line1: str, line2: str = "",
                duration_ms: int = 4000, warn: bool = False, parent=None):
\
\
\
\
\
\
       
    owns_root = parent is None
    try:
        root = tk.Tk() if owns_root else tk.Toplevel(parent)
    except Exception:
        return

    try:
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-alpha", 0.0)
        except Exception:
            pass

        icon_color = WARN if warn else OK
        icon_char  = "⚠" if warn else "✓"

        wrap = tk.Frame(root, bg=BORDER, padx=1, pady=1)
        wrap.pack()
        card = tk.Frame(wrap, bg=BG_CARD, padx=14, pady=10)
        card.pack()

        hdr = tk.Frame(card, bg=BG_CARD)
        hdr.pack(anchor="w", fill="x")
        tk.Label(hdr, text="☁", font=("Segoe UI Emoji", 14),
                 bg=BG_CARD, fg=ACCENT).pack(side="left", padx=(0, 8))
        tk.Label(hdr, text=title, font=("Segoe UI", 10, "bold"),
                 bg=BG_CARD, fg=TEXT_PRI).pack(side="left")

        body = tk.Frame(card, bg=BG_CARD)
        body.pack(anchor="w", fill="x", pady=(6, 0))
        tk.Label(body, text=icon_char, font=("Segoe UI", 11, "bold"),
                 bg=BG_CARD, fg=icon_color).pack(side="left", padx=(0, 8))
        txt = tk.Frame(body, bg=BG_CARD)
        txt.pack(side="left", fill="x", expand=True)
        tk.Label(txt, text=line1, font=("Segoe UI", 9),
                 bg=BG_CARD, fg=TEXT_PRI, anchor="w",
                 justify="left").pack(anchor="w")
        if line2:
            tk.Label(txt, text=line2, font=("Segoe UI", 8),
                     bg=BG_CARD, fg=TEXT_SEC, anchor="w",
                     justify="left").pack(anchor="w", pady=(2, 0))

        root.update_idletasks()
        w, h = root.winfo_width(), root.winfo_height()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"+{sw - w - 20}+{sh - h - 60}")

        def dismiss(_=None):
            try: root.destroy()
            except Exception: pass

        for wdg in (root, wrap, card, hdr, body, txt):
            wdg.bind("<Button-1>", dismiss)

        def fade_in(alpha=0.0):
            alpha += 0.1
            if alpha >= 1.0:
                try: root.attributes("-alpha", 1.0)
                except Exception: pass
                return
            try:
                root.attributes("-alpha", alpha)
                root.after(15, lambda: fade_in(alpha))
            except Exception:
                pass

        fade_in()
        root.after(duration_ms, dismiss)
        if owns_root:
            root.mainloop()
    except Exception:
        try: root.destroy()
        except Exception: pass


                                                                                
def _humanize_ago(seconds: float) -> str:
                                                               
    s = int(max(0, seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


                                                                                
def find_game_exe_candidates(game_folder: Path) -> list:
\
\
\
\
\
\
\
\
\
       
    if not game_folder.exists():
        return []

    skip_names = {
        "unins000.exe", "uninstall.exe", "installer.exe",
        "vcredist_x64.exe", "vcredist_x86.exe", "dxsetup.exe",
        "directx.exe", "launcher.exe", "helper.exe",
        "crashreportclient.exe", "unrealcefsubprocess.exe",
        "steamerrorreporter.exe", "cefsharphelper.exe",
    }

    scored = []
    for p in game_folder.rglob("*.exe"):
        try:
            lname = p.name.lower()
            if lname in skip_names:
                continue
            if lname.startswith("vcredist") or lname.startswith("dxsetup"):
                continue

            parts_lower = [part.lower() for part in p.parts]
            score = 2

            if "binaries" in parts_lower and "win64" in parts_lower:
                score = 4
            if p.parent == game_folder:
                score = max(score, 6)
            if lname.endswith("-win64-shipping.exe"):
                score = 10
            elif lname.endswith("-win32-shipping.exe"):
                score = 8

            scored.append((score, p))
        except Exception:
            pass

    scored.sort(key=lambda x: (-x[0], str(x[1])))
    return scored


def pick_game_exe(parent, game_folder: Path) -> Path | None:
\
\
\
       
    candidates = find_game_exe_candidates(game_folder)
    if not candidates:
        messagebox.showerror(
            "Save Sync",
            f"No .exe found under:\n{game_folder}\n\n"
            "Pick a different folder.",
            parent=parent,
        )
        return None

    if len(candidates) == 1:
        return candidates[0][1]

    win = tk.Toplevel(parent)
    win.title("Select the game's main exe")
    win.geometry("640x420")
    win.configure(bg=BG_CARD)
    win.transient(parent)
    win.grab_set()

    main = tk.Frame(win, bg=BG_CARD, padx=16, pady=16)
    main.pack(fill="both", expand=True)

    tk.Label(main, text="Which file launches the game?",
             font=("Segoe UI", 12, "bold"),
             bg=BG_CARD, fg=TEXT_PRI).pack(anchor="w")
    tk.Label(main,
             text="Pick the exe that Steam runs when you click Play.\n"
                  "For UE5, that's usually *-Win64-Shipping.exe.",
             font=("Segoe UI", 9),
             bg=BG_CARD, fg=TEXT_SEC, justify="left").pack(anchor="w", pady=(2, 10))

    lb = tk.Listbox(main, bg=BG_INPUT, fg=TEXT_PRI,
                    selectbackground=ACCENT_DIM, selectforeground=ACCENT,
                    font=("Segoe UI", 9), relief="flat", highlightthickness=0)
    lb.pack(fill="both", expand=True)

    for _score, p in candidates:
        try:
            rel = p.relative_to(game_folder)
        except Exception:
            rel = p.name
        lb.insert(tk.END, str(rel))

    lb.selection_set(0)

    chosen = {"path": None}

    def confirm():
        sel = lb.curselection()
        if not sel:
            return
        chosen["path"] = candidates[sel[0]][1]
        win.destroy()

    btn = tk.Frame(main, bg=BG_CARD)
    btn.pack(fill="x", pady=(10, 0))
    tk.Button(btn, text="Use this exe", command=confirm,
              bg=ACCENT_DIM, fg=ACCENT, font=("Segoe UI", 9, "bold"),
              relief="flat", padx=14, pady=5,
              cursor="hand2").pack(side="right")
    tk.Button(btn, text="Cancel", command=win.destroy,
              bg=BG_INPUT, fg=TEXT_SEC, font=("Segoe UI", 9),
              relief="flat", padx=14, pady=5,
              cursor="hand2").pack(side="right", padx=(0, 8))

    win.wait_window()
    return chosen["path"]


def deploy_proxy_to_game(game_dir: Path, game_exe: Path, appid: int,
                         game_name: str) -> tuple:
                                                                                      
    proxy_src = sg_paths.assets_dir() / "version.dll"
    if not proxy_src.exists():
        return False, f"version.dll not found in assets:\n{sg_paths.assets_dir()}"

    target_dir = game_exe.parent
    target_dll = target_dir / "version.dll"
    marker     = target_dir / ".steam_lookup_save_gd.json"

    try:
        if target_dll.exists():
            try: target_dll.unlink()
            except Exception: pass
        shutil.copy(proxy_src, target_dll)
    except Exception as e:
        return False, f"Failed to copy version.dll: {e}"

    try:
        marker.write_text(json.dumps({
            "appid":       appid,
            "name":        game_name,
            "enrolled_at": time.time(),
        }, indent=2), encoding="utf-8")
    except Exception as e:
        return False, f"Failed to write marker: {e}"

    return True, str(target_dir)


PROXY_MARKER = ".steam_lookup_save_gd.json"


def _marker_matches(marker: Path, appid) -> bool:
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        return str(data.get("appid")) == str(appid)
    except Exception:
        return False


def remove_proxy_from_game(appid, proxy_dirs, deployed_dirs) -> tuple:
\
\
\
\
\
\
\
\
       
    targets = []
    for d in proxy_dirs or []:
        p = Path(d)
        if p not in targets:
            targets.append(p)

    if not targets:
        for d in deployed_dirs or []:
            try:
                for root, _dirs, files in os.walk(d):
                    if PROXY_MARKER in files and _marker_matches(
                            Path(root) / PROXY_MARKER, appid):
                        targets.append(Path(root))
            except Exception:
                pass

    removed, failed = [], []
    for t in targets:
        try:
            dll = t / "version.dll"
            marker = t / PROXY_MARKER
            if dll.exists():
                dll.unlink()
            if marker.exists():
                marker.unlink()
            removed.append(str(t))
        except Exception as e:
            failed.append((str(t), str(e)))
    return removed, failed


def find_deployed_proxy_dirs(game: dict) -> list:
                                                                                 
    found = []
    for raw in (game.get("proxy_dirs") or []):
        try:
            folder = Path(raw)
            if (folder / "version.dll").is_file() and folder not in found:
                found.append(folder)
        except (TypeError, OSError):
            pass

    if found:
        return found

                                                                            
                                                                            
    for raw in (game.get("deployed_dirs") or []):
        try:
            base = Path(raw)
            if not base.is_dir():
                continue
            for root, _dirs, files in os.walk(base):
                if PROXY_MARKER in files:
                    marker = Path(root) / PROXY_MARKER
                    if _marker_matches(marker, game.get("appid")):
                        folder = Path(root)
                        if (folder / "version.dll").is_file() and folder not in found:
                            found.append(folder)
        except (TypeError, OSError):
            pass
    return found


def record_deploy(entry: dict, appid, game_dir: Path, proxy_dir: str):
                                                                      
    dirs = list(entry.get("deployed_dirs") or [])
    if str(game_dir) not in dirs:
        dirs.append(str(game_dir))
    proxy = list(entry.get("proxy_dirs") or [])
    if proxy_dir and proxy_dir not in proxy:
        proxy.append(proxy_dir)
    try:
        sg_manifest.update_game(appid, deployed_dirs=dirs, proxy_dirs=proxy)
    except TypeError:
        sg_manifest.update_game(appid, deployed_dirs=dirs)


                                                                                
class SaveSyncApp(tk.Tk):
    def __init__(self, background: bool = False):
        super().__init__()
        self.title("Save Sync")
        self.geometry("900x640")
        self.minsize(760, 500)
        self.configure(bg=BG_DARK)

        self.background_mode  = background
        self.silence_warnings = sg_paths.load_silence_warnings()
        self.startup_enabled  = sg_paths.is_startup_enabled()
        self.steam_path       = sg_manifest.detect_steam_path()

        self._auth_poll_job       = None
        self._auth_watcher_active = False
        self._auth_watch_start    = 0.0
        self._drive_status_cache   = {}                                       

                                
        self._bg_running       = False
        self._bg_notified      = {}                                                     
        self._bg_warned_auth   = False

                                                                       
        self._ui_q = queue.Queue()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()
        self.after(100, self._pump_ui)

        if background:
            self.withdraw()
            self.after(BG_FIRST_TICK_MS, self._background_tick)

                                                                         
        self.after(300, self._sync_games_json_on_startup)
                                                                           
        self._weak_refreshing = False
        self.after(2500, self._refresh_weak_paths_async)

                                                                                

    def _ui(self, fn):
                                                                         
        self._ui_q.put(fn)

    def _pump_ui(self):
        try:
            while True:
                fn = self._ui_q.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
        except queue.Empty:
            pass
        try:
            self.after(100, self._pump_ui)
        except tk.TclError:
            pass

                                                                                

    def _build_ui(self):
        hdr = tk.Frame(self, bg=BG_MID, height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="💾  Save Sync", font=("Segoe UI", 15, "bold"),
                 bg=BG_MID, fg=ACCENT).pack(side="left", padx=16)

        tk.Button(hdr, text="📚  Scan Library",
                  command=self._open_library_scan,
                  bg=BG_CARD, fg=TEXT_PRI,
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=12, pady=4,
                  cursor="hand2").pack(side="left", padx=(8, 0))

        tk.Button(hdr, text="📂  Add Folder",
                  command=self._open_add_folder,
                  bg=BG_CARD, fg=TEXT_PRI,
                  font=("Segoe UI", 9),
                  relief="flat", padx=12, pady=4,
                  cursor="hand2").pack(side="left", padx=(6, 0))

        self._auth_status = tk.Label(
            hdr, text="", font=("Segoe UI", 9, "bold"),
            bg=BG_MID, fg=TEXT_MUTED,
        )
        self._auth_status.pack(side="right", padx=16)
        self._auth_btn = None
        self._refresh_auth_status()

                     
        toggles = tk.Frame(self, bg=BG_MID, height=38)
        toggles.pack(fill="x")
        toggles.pack_propagate(False)

        self._silence_var = tk.BooleanVar(value=self.silence_warnings)
        tk.Checkbutton(
            toggles, text="🔕  Silence warnings (not recommended)",
            variable=self._silence_var, command=self._toggle_silence,
            bg=BG_MID, fg=TEXT_PRI, selectcolor=BG_CARD,
            activebackground=BG_MID, activeforeground=ACCENT,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(16, 20))

        self._startup_var = tk.BooleanVar(value=self.startup_enabled)
        tk.Checkbutton(
            toggles, text="🚀  Launch on startup",
            variable=self._startup_var, command=self._toggle_startup,
            bg=BG_MID, fg=TEXT_PRI, selectcolor=BG_CARD,
            activebackground=BG_MID, activeforeground=ACCENT,
            font=("Segoe UI", 9),
        ).pack(side="left")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

                              
        self._list_outer = tk.Frame(self, bg=BG_DARK)
        self._list_outer.pack(fill="both", expand=True, padx=16, pady=12)

        self._canvas = tk.Canvas(self._list_outer, bg=BG_DARK, highlightthickness=0)
        self._scrollbar = tk.Scrollbar(self._list_outer, orient="vertical",
                                       command=self._canvas.yview)
        self._inner = tk.Frame(self._canvas, bg=BG_DARK)
        self._win = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._scrollbar.pack(side="right", fill="y")

        self._inner.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfig(self._win, width=e.width),
        )
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        self._render_games()

                
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        footer = tk.Frame(self, bg=BG_MID, height=40)
        footer.pack(fill="x")
        footer.pack_propagate(False)

        tk.Button(footer, text="Close", command=self._on_close,
                  bg=BG_INPUT, fg=TEXT_SEC, font=("Segoe UI", 9),
                  relief="flat", padx=14, pady=4,
                  cursor="hand2").pack(side="right", padx=12, pady=6)

        tk.Button(footer, text="↻ Refresh", command=self._render_games,
                  bg=BG_INPUT, fg=TEXT_PRI, font=("Segoe UI", 9),
                  relief="flat", padx=14, pady=4,
                  cursor="hand2").pack(side="right", pady=6)

    def _on_mousewheel(self, event):
        try:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _on_close(self):
        self._auth_watcher_active = False
        try:
            self.destroy()
        except Exception:
            pass

                                                                                

    def _render_games(self):
        for w in self._inner.winfo_children():
            w.destroy()

        games = sg_manifest.all_games()
        if not games:
            tk.Label(self._inner,
                     text="No games enrolled.\n\n"
                          "Click 📚 Scan Library to add from your Steam library,\n"
                          "or 📂 Add Folder to point at any game.",
                     font=("Segoe UI", 11),
                     bg=BG_DARK, fg=TEXT_MUTED,
                     justify="center").pack(pady=80)
            return

        for g in games:
            self._make_card(g)

    def _make_card(self, game):
        card = tk.Frame(self._inner, bg=BG_CARD, padx=14, pady=12)
        card.pack(fill="x", pady=(0, 8))

        top = tk.Frame(card, bg=BG_CARD)
        top.pack(fill="x")

        left = tk.Frame(top, bg=BG_CARD)
        left.pack(side="left", fill="x", expand=True)

        tk.Label(left, text=game.get("name", f"AppID {game['appid']}"),
                 font=("Segoe UI", 11, "bold"),
                 bg=BG_CARD, fg=TEXT_PRI, anchor="w").pack(anchor="w")

        appid = game["appid"]
        save_path = game.get("save_path", "")
        source = game.get("save_path_source", "") or "unknown"

        info_parts = [f"AppID {appid}"]
        if save_path:
            info_parts.append(f"Source: {source}")
        tk.Label(left, text="  •  ".join(info_parts),
                 font=("Segoe UI", 8), bg=BG_CARD, fg=TEXT_MUTED,
                 anchor="w").pack(anchor="w", pady=(2, 0))

        if save_path:
            tk.Label(left, text=f"📁  {save_path}",
                     font=("Segoe UI", 8), bg=BG_CARD, fg=TEXT_SEC,
                     anchor="w", wraplength=560, justify="left").pack(anchor="w", pady=(2, 0))
        else:
            tk.Label(left, text="⚠  Save path not set — click 'Set Path'",
                     font=("Segoe UI", 8), bg=BG_CARD, fg=WARN,
                     anchor="w").pack(anchor="w", pady=(2, 0))

                                                           
        playtime = None
        if save_path and self.steam_path:
            try:
                playtime = steam_local.get_local_playtime(appid, self.steam_path)
            except Exception:
                playtime = None
        if playtime is not None:
            hrs = playtime // 60
            mins = playtime % 60
            tk.Label(left, text=f"⏱  {hrs}h {mins}m on this PC",
                     font=("Segoe UI", 8), bg=BG_CARD, fg=TEXT_MUTED,
                     anchor="w").pack(anchor="w", pady=(2, 0))

                                                                      
                                                           
        last_sync = game.get("last_sync")
        if last_sync:
            try:
                ago = _humanize_ago(time.time() - float(last_sync))
                last_kind = "synced"
                lu = game.get("last_upload") or 0
                ld = game.get("last_download") or 0
                if lu and lu >= ld:
                    last_kind = "uploaded"
                elif ld:
                    last_kind = "downloaded"
                tk.Label(left, text=f"🔄  Last {last_kind} {ago} ago",
                         font=("Segoe UI", 8), bg=BG_CARD, fg=TEXT_SEC,
                         anchor="w").pack(anchor="w", pady=(2, 0))
            except (TypeError, ValueError):
                pass

                                                                             
        proxy_dirs_found = find_deployed_proxy_dirs(game)
        dll_status = tk.Label(
            left,
            text=("✓ version.dll found" if proxy_dirs_found else "⚠ version.dll not found"),
            font=("Segoe UI", 8, "bold"),
            bg=BG_CARD, fg=(OK if proxy_dirs_found else WARN),
            anchor="w",
        )
        dll_status.pack(anchor="w", pady=(4, 0))

        right = tk.Frame(top, bg=BG_CARD)
        right.pack(side="right", anchor="ne")

        status_lbl = tk.Label(right, text="",
                              font=("Segoe UI", 8, "bold"),
                              bg=BG_CARD, fg=TEXT_MUTED, anchor="e")
        status_lbl.pack(anchor="e", pady=(0, 6))

        btn_row = tk.Frame(right, bg=BG_CARD)
        btn_row.pack(anchor="e")

        def do_upload():
            self._manual_upload(game)

        def do_download():
            self._manual_download(game)

        def do_set_path():
            folder = filedialog.askdirectory(
                title=f"Select save folder for {game.get('name', appid)}")
            if not folder:
                return
                                                                    
            sg_manifest.set_manual_path(appid, folder, self.steam_path)
            self._push_games_json()
            self._render_games()

        def do_load_dll():
            self._load_dll_for_game(game)

        def do_remove():
            if not messagebox.askyesno(
                "Remove game",
                f"Remove {game.get('name', appid)} from Save Sync?\n\n"
                "This also deletes the version.dll hook from the game folder.\n"
                "Your saves (local and on Google Drive) are NOT touched.",
                parent=self,
            ):
                return
            self._remove_game(game)

        def mk_btn(text, cmd, primary=False, danger=False):
            if primary:
                bg, fg = ACCENT_DIM, ACCENT
            elif danger:
                bg, fg = BG_INPUT, DANGER
            else:
                bg, fg = BG_INPUT, TEXT_PRI
            b = tk.Button(btn_row, text=text, command=cmd,
                          bg=bg, fg=fg,
                          font=("Segoe UI", 8, "bold" if primary else "normal"),
                          relief="flat", padx=10, pady=3, cursor="hand2")
            b.pack(side="left", padx=(0, 4))
            return b

        if save_path:
            mk_btn("⬆ Upload",   do_upload, primary=True)
            mk_btn("⬇ Download", do_download)
            mk_btn("📁 Path",    do_set_path)
        else:
            mk_btn("📁 Set Path", do_set_path, primary=True)

        if not proxy_dirs_found:
            mk_btn("Load DLL", do_load_dll, primary=True)
        mk_btn("✕", do_remove, danger=True)

                                                                              
        if save_path:
            auto_var = tk.BooleanVar(value=bool(game.get("auto_download", False)))

            def toggle_auto():
                want = auto_var.get()
                if want:
                    if not messagebox.askyesno(
                        "Enable auto-download?",
                        f"Auto-download for {game.get('name', appid)}?\n\n"
                        "⚠ When Google Drive has a newer save, this game's "
                        "local saves will be REPLACED automatically in the "
                        "background.\n\n"
                        "Your previous local save is archived to Google Drive "
                        "history first, so nothing is lost permanently.\n\n"
                        "Enable auto-download?",
                        parent=self,
                    ):
                        auto_var.set(False)
                        return
                sg_manifest.update_game(appid, auto_download=want)
                self._push_games_json()

            tk.Checkbutton(btn_row, text="Auto ⬇", variable=auto_var,
                           command=toggle_auto,
                           bg=BG_CARD, fg=TEXT_SEC, selectcolor=BG_INPUT,
                           activebackground=BG_CARD, activeforeground=ACCENT,
                           font=("Segoe UI", 8), cursor="hand2",
                           bd=0, highlightthickness=0).pack(side="left", padx=(6, 0))

        self._check_drive_status(appid, save_path, status_lbl)

    def _load_dll_for_game(self, game):
                                                                                   
        appid = game["appid"]
        name = game.get("name", f"AppID {appid}")
        folder = filedialog.askdirectory(
            parent=self,
            title=f"Select the install folder for {name}",
        )
        if not folder:
            return

        game_dir = Path(folder)
        game_exe = pick_game_exe(self, game_dir)
        if not game_exe:
            return

        ok, msg = deploy_proxy_to_game(game_dir, game_exe, appid, name)
        if not ok:
            messagebox.showerror("Save Sync", f"Couldn't load version.dll for {name}:\n\n{msg}", parent=self)
            return

                                                                                 
                                                                                
        record_deploy(game, appid, game_dir, msg)
        self._render_games()
        messagebox.showinfo(
            "Save Sync",
            f"version.dll loaded for {name}.\n\nInstalled next to: {game_exe.name}\nFolder: {msg}",
            parent=self,
        )

    def _remove_game(self, game):
                                                                                
        appid = game["appid"]
        name = game.get("name", f"AppID {appid}")
        proxy_dirs = list(game.get("proxy_dirs") or [])
        deployed = list(game.get("deployed_dirs") or [])

        def worker():
            removed, failed = remove_proxy_from_game(appid, proxy_dirs, deployed)
            self._ui(lambda: self._after_remove(appid, name, removed, failed))

        self._set_busy(True)
        threading.Thread(target=worker, daemon=True).start()

    def _after_remove(self, appid, name, removed, failed):
        self._set_busy(False)
        if failed:
            detail = "\n".join(f"{d}\n  {e}" for d, e in failed[:3])
            messagebox.showerror(
                "Save Sync",
                f"Couldn't remove version.dll for {name}.\n\n"
                f"Close the game and try again.\n\n{detail}",
                parent=self,
            )
            return                                       

        sg_manifest.unenroll_game(appid)
        self._drive_status_cache.pop(appid, None)
        self._push_games_json()
        self._render_games()
        _show_toast(
            "Save Sync",
            f"{name} removed",
            "version.dll deleted from the game folder." if removed
            else "No version.dll was found in the game folder.",
            parent=self,
        )

    def _check_drive_status(self, appid: int, save_path: str, status_lbl):
        if not save_path or not sg_paths.token_file().exists():
            return

        now = time.time()
        cached = self._drive_status_cache.get(appid)
        if cached and now - cached[1] < 60:
            self._apply_cloud_badge(status_lbl, cached[0])
            return

        def worker():
            try:
                client = sg_sync.DriveClient(str(sg_paths.token_file()))
                if not client.authenticate():
                    return
                info = sg_sync.compare_game(
                    appid, save_path, client, self.steam_path)
                self._drive_status_cache[appid] = (info, time.time())
                self._ui(lambda: self._apply_cloud_badge(status_lbl, info))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _apply_cloud_badge(self, status_lbl, info):
                                                                                      
        try:
            if not status_lbl.winfo_exists():
                return
        except tk.TclError:
            return

        state = info.get("state")
        if state == "in_sync":
            status_lbl.configure(text="✓ In sync with Google Drive", fg=OK)
        elif state == "cloud_newer":
            status_lbl.configure(text="⚠ Newer on Google Drive", fg=WARN)
        elif state == "local_newer":
            status_lbl.configure(text="⬆ Newer on this PC", fg=ACCENT)
        elif state == "conflict":
            status_lbl.configure(text="⚠ Conflict: changed on both", fg=DANGER)
        elif state == "no_cloud":
            status_lbl.configure(text="☁ Nothing on Google Drive yet", fg=TEXT_MUTED)
        else:
            status_lbl.configure(text="", fg=TEXT_MUTED)

                                                                                

    def _manual_upload(self, game):
        appid = game["appid"]
        name = game.get("name", f"AppID {appid}")
        save_path = game.get("save_path")
        if not save_path or not os.path.isdir(save_path):
            messagebox.showerror("Save Sync", "Save path is not set.", parent=self)
            return

        if not messagebox.askyesno(
            "Confirm upload",
            f"Upload local saves to Google Drive for:\n{name}\n\n"
            "⚠ This will REPLACE the cloud copy.\n"
            "The previous cloud copy will be archived to history.",
            parent=self,
        ):
            return

        def worker():
            try:
                client = sg_sync.DriveClient(str(sg_paths.token_file()))
                if not client.authenticate():
                    self._ui(lambda: self._fail_manual("Not authorized."))
                    return
                result = sg_sync.sync_game(
                    appid, save_path, client, auto_download=False,
                    steam_path=self.steam_path, direction="upload")
                self._ui(lambda: self._after_manual(result, name, appid))
            except Exception as e:
                self._ui(lambda: self._fail_manual(f"Upload failed:\n{e}"))

        self._set_busy(True)
        threading.Thread(target=worker, daemon=True).start()

    def _manual_download(self, game):
        appid = game["appid"]
        name = game.get("name", f"AppID {appid}")
        save_path = game.get("save_path")
        if not save_path or not os.path.isdir(save_path):
            messagebox.showerror("Save Sync", "Save path is not set.", parent=self)
            return

        if not messagebox.askyesno(
            "Confirm download",
            f"Download cloud saves from Google Drive for:\n{name}\n\n"
            "⚠ This will REPLACE your local saves.\n"
            "Your current local save is archived to Google Drive history first.",
            parent=self,
        ):
            return

        def worker():
            try:
                client = sg_sync.DriveClient(str(sg_paths.token_file()))
                if not client.authenticate():
                    self._ui(lambda: self._fail_manual("Not authorized."))
                    return
                result = sg_sync.sync_game(
                    appid, save_path, client, auto_download=True,
                    steam_path=self.steam_path, direction="download")
                self._ui(lambda: self._after_manual(result, name, appid))
            except Exception as e:
                self._ui(lambda: self._fail_manual(f"Download failed:\n{e}"))

        self._set_busy(True)
        threading.Thread(target=worker, daemon=True).start()

    def _fail_manual(self, text):
        self._set_busy(False)
        messagebox.showerror("Save Sync", text, parent=self)

    def _after_manual(self, result, name, appid=None):
        self._set_busy(False)
        self._drive_status_cache.clear()

        action = result.get("action", "?")
        msg = result.get("message", "")
        warn_text = result.get("warning") or ""

                                                                           
                                                
        if appid is not None and action in ("uploaded", "downloaded"):
            now = time.time()
            fields = {"last_sync": now}
            if action == "uploaded":
                fields["last_upload"] = now
            else:
                fields["last_download"] = now
            try:
                sg_manifest.update_game(appid, **fields)
                self._push_games_json()
            except Exception:
                pass

        if action == "skipped":
            messagebox.showinfo("Save Sync", f"{name}\n\n{msg}", parent=self)
        elif action == "error":
            messagebox.showerror("Save Sync", f"{name}\n\n{msg}", parent=self)
        else:
            body = f"{name}\n\n{msg}"
            if warn_text and not self.silence_warnings:
                body += f"\n\n{warn_text}"
            messagebox.showinfo("Save Sync", body, parent=self)

        self._render_games()

    def _set_busy(self, busy: bool):
        try:
            self.configure(cursor="watch" if busy else "")
        except tk.TclError:
            pass

                                                                                

    def _open_add_folder(self):
                                                                                     
        folder = filedialog.askdirectory(
            title="Select the game's install folder (contains game.exe)")
        if not folder:
            return
        game_dir = Path(folder)

        game_exe = pick_game_exe(self, game_dir)
        if not game_exe:
            return

        guess_name = game_exe.stem
        appid = self._ask_appid(guess_name)
        if not appid:
            return

        entry = sg_manifest.enroll_and_resolve(appid, guess_name, self.steam_path)
        if not entry:
            messagebox.showerror("Save Sync", "Failed to enroll game.")
            return

        ok, msg = deploy_proxy_to_game(game_dir, game_exe, appid, guess_name)
        if not ok:
            messagebox.showwarning("Save Sync", f"Enrolled, but: {msg}")
        else:
            record_deploy(entry, appid, game_dir, msg)

        self._push_games_json()
        self._render_games()
        self.after(15000, self._refresh_weak_paths_async)                         

        path = entry.get("save_path") or ""
        messagebox.showinfo(
            "Save Sync",
            f"Enrolled: {guess_name}\n"
            f"AppID: {appid}\n\n"
            f"Save path: {path or '(not found — set it manually on the card)'}\n"
            f"version.dll deployed next to: {game_exe.name}"
        )

    def _ask_appid(self, guess_name: str) -> int | None:
                                                                    
        win = tk.Toplevel(self)
        win.title("Enter Steam AppID")
        win.geometry("420x180")
        win.configure(bg=BG_CARD)
        win.transient(self)
        win.grab_set()

        tk.Label(win, text=f"Steam AppID for: {guess_name}",
                 font=("Segoe UI", 11, "bold"),
                 bg=BG_CARD, fg=TEXT_PRI).pack(anchor="w", padx=16, pady=(16, 6))
        tk.Label(win,
                 text="You can find this in the Steam URL:\n"
                      "store.steampowered.com/app/<APPID>/...",
                 font=("Segoe UI", 9),
                 bg=BG_CARD, fg=TEXT_SEC, justify="left").pack(anchor="w", padx=16, pady=(0, 10))

        var = tk.StringVar()
        entry = tk.Entry(win, textvariable=var, font=("Segoe UI", 11),
                         bg=BG_INPUT, fg=TEXT_PRI, insertbackground=ACCENT,
                         relief="flat", highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=ACCENT, bd=4)
        entry.pack(fill="x", padx=16, pady=(0, 14))
        entry.focus()

        result = {"appid": None}

        def confirm(_=None):
            s = var.get().strip()
            if not s.isdigit():
                return
            result["appid"] = int(s)
            win.destroy()

        entry.bind("<Return>", confirm)
        tk.Button(win, text="OK", command=confirm,
                  bg=ACCENT_DIM, fg=ACCENT, font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=14, pady=5,
                  cursor="hand2").pack(side="right", padx=16)

        win.wait_window()
        return result["appid"]

    def _open_library_scan(self):
                                                                           
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
        win.geometry("760x580")
        win.configure(bg=BG_CARD)
        win.transient(self)
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
        lb = tk.Listbox(list_frame, selectmode="extended",
                        bg=BG_INPUT, fg=TEXT_PRI,
                        selectbackground=ACCENT_DIM, selectforeground=ACCENT,
                        font=("Segoe UI", 10),
                        relief="flat", highlightthickness=0, yscrollcommand=sb.set)
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
                messagebox.showinfo("Save Sync", "Select one or more games first.",
                                    parent=win)
                return

            added = 0
            needs_path = []
            no_exe = []
            failed = []

            for i in sel:
                g = displayed[i]
                appid = g["appid"]
                name  = g["name"]
                game_dir = Path(g["installdir"])
                try:
                    game_exe = pick_game_exe(win, game_dir)
                    if not game_exe:
                        no_exe.append(name)
                        continue

                    entry = sg_manifest.enroll_and_resolve(
                        appid, name, self.steam_path)
                    if not entry:
                        failed.append(name)
                        continue

                    added += 1
                    if not entry.get("save_path"):
                        needs_path.append(name)

                    ok, msg = deploy_proxy_to_game(game_dir, game_exe, appid, name)
                    if not ok:
                        failed.append(f"{name}: {msg}")
                    else:
                        record_deploy(entry, appid, game_dir, msg)
                except Exception as e:
                    failed.append(f"{name}: {e}")

            self._push_games_json()
            self.after(15000, self._refresh_weak_paths_async)                         

            summary = f"Added {added} games."
            if needs_path:
                preview = "\n".join(needs_path[:5])
                if len(needs_path) > 5:
                    preview += f"\n... and {len(needs_path) - 5} more"
                summary += (f"\n\nSave path not found for:\n{preview}\n\n"
                            "Use 'Set Path' on those cards.")
            if no_exe:
                summary += "\n\nSkipped (no exe selected):\n" + "\n".join(no_exe[:5])
            if failed:
                summary += "\n\nFailed:\n" + "\n".join(failed[:3])

            messagebox.showinfo("Save Sync", summary, parent=win)
            win.destroy()
            self._render_games()

        tk.Button(btn_row, text="Add Selected", command=add_selected,
                  bg=ACCENT_DIM, fg=ACCENT, font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=14, pady=5,
                  cursor="hand2").pack(side="left")
        tk.Button(btn_row, text="Select All",
                  command=lambda: lb.selection_set(0, tk.END),
                  bg=BG_INPUT, fg=TEXT_PRI, font=("Segoe UI", 9),
                  relief="flat", padx=14, pady=5,
                  cursor="hand2").pack(side="left", padx=(6, 0))
        tk.Button(btn_row, text="Cancel", command=win.destroy,
                  bg=BG_INPUT, fg=TEXT_SEC, font=("Segoe UI", 9),
                  relief="flat", padx=14, pady=5,
                  cursor="hand2").pack(side="right")

                                                                                

    def _refresh_auth_status(self):
        try:
            if sg_paths.token_file().exists():
                self._auth_status.configure(text="☁ Authorized", fg=ACCENT)
                if self._auth_btn and self._auth_btn.winfo_exists():
                    self._auth_btn.destroy()
                    self._auth_btn = None
            else:
                self._auth_status.configure(text="⚠ Not authorized", fg=DANGER)
                if not (self._auth_btn and self._auth_btn.winfo_exists()):
                    self._auth_btn = tk.Button(
                        self, text="Authorize Google Drive",
                        command=self._run_auth_flow,
                        bg=ACCENT_DIM, fg=ACCENT,
                        font=("Segoe UI", 9, "bold"),
                        relief="flat", padx=12, pady=4,
                        cursor="hand2",
                    )
                    self._auth_btn.place(relx=1.0, rely=0.0, anchor="ne", x=-150, y=12)
        except tk.TclError:
            pass

    def _run_auth_flow(self):
        exe = sg_paths.save_gd_exe()
        if not exe.exists():
            messagebox.showerror(
                "Save Sync",
                f"save_gd.exe not found at:\n{exe}"
            )
            return
        subprocess.Popen([str(exe), "--setup"], cwd=str(exe.parent))
        self._start_auth_watcher()

    def _start_auth_watcher(self):
        if self._auth_watcher_active:
            return
        self._auth_watcher_active = True
        self._auth_watch_start = time.time()

        def watch():
            while self._auth_watcher_active:
                if sg_paths.token_file().exists():
                    self._auth_watcher_active = False
                    self._ui(self._on_auth_success)
                    return
                if time.time() - self._auth_watch_start > 300:
                    self._auth_watcher_active = False
                    return
                time.sleep(1)

        threading.Thread(target=watch, daemon=True).start()

    def _on_auth_success(self):
        self._refresh_auth_status()
        self._sync_games_json_on_startup()
        self._render_games()

                                                                                

    def _toggle_silence(self):
        self.silence_warnings = self._silence_var.get()
        sg_paths.save_silence_warnings(self.silence_warnings)

    def _toggle_startup(self):
        want = self._startup_var.get()
        if want:
            ok, msg = sg_paths.enable_startup()
            if not ok:
                messagebox.showerror("Launch on startup", msg)
                self._startup_var.set(False)
                return
            messagebox.showinfo("Launch on startup", msg)
        else:
            ok, msg = sg_paths.disable_startup()
            if not ok:
                messagebox.showerror("Launch on startup", msg)
                self._startup_var.set(True)
                return

                                                                                

    def _pull_and_merge_games_json(self, client) -> int:
\
\
\
           
        remote = sg_sync.pull_games_json(client)
        if not remote or not remote.get("games"):
            return 0

        with sg_manifest._LOCK:
            local = sg_manifest.load_manifest()
            before = set(str(k) for k in (local.get("games") or {}).keys())
            merged = sg_sync.merge_games_json(local, remote, self.steam_path)
            sg_manifest.save_manifest(merged)
            after = set(str(k) for k in (merged.get("games") or {}).keys())
        return len(after - before)

    def _sync_games_json_on_startup(self):
                                                                                    
        if not sg_paths.token_file().exists():
            return

        def worker():
            try:
                client = sg_sync.DriveClient(str(sg_paths.token_file()))
                if not client.authenticate():
                    return
                new_count = self._pull_and_merge_games_json(client)
                if new_count:
                    def done():
                        self._render_games()
                        _show_toast(
                            "Save Sync",
                            f"Restored {new_count} game(s) from Google Drive",
                            parent=self,
                        )
                    self._ui(done)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _push_games_json(self):
                                                                         
        if not sg_paths.token_file().exists():
            return
        data = sg_manifest.load_manifest()

        def worker():
            try:
                client = sg_sync.DriveClient(str(sg_paths.token_file()))
                if not client.authenticate():
                    return
                sg_sync.push_games_json(client, data)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

                                                                                
    def _refresh_weak_paths_async(self):
                                                                                  
        if self._weak_refreshing:
            return
        self._weak_refreshing = True

        def worker():
            changed = []
            try:
                changed = sg_manifest.refresh_weak_paths(self.steam_path)
            except Exception:
                changed = []
            finally:
                self._weak_refreshing = False
            if changed:
                self._ui(lambda: self._after_paths_refreshed(changed))

        threading.Thread(target=worker, daemon=True).start()

    def _after_paths_refreshed(self, changed):
        self._drive_status_cache.clear()
        self._render_games()
        self._push_games_json()
        shown = ", ".join(name for name, _old, _new in changed[:3])
        if len(changed) > 3:
            shown += f" +{len(changed) - 3} more"
        _show_toast("Save Sync", "Save path corrected from PCGamingWiki",
                    shown, duration_ms=6000, parent=self)
        
    def _background_tick(self):
\
\
\
\
\
\
\
\
\
           
        try:
            self.after(BG_INTERVAL_MS, self._background_tick)
        except tk.TclError:
            return

        if self._bg_running:
            return

        if not sg_paths.token_file().exists():
            if not self._bg_warned_auth:
                self._bg_warned_auth = True
                _show_toast(
                    "Save Sync",
                    "Google Drive is not authorized",
                    "Open Save Sync and click 'Authorize Google Drive'.",
                    duration_ms=6000, warn=True, parent=self,
                )
            return

        self._bg_running = True

        def worker():
            newer_games = []
            conflict_games = []
            auto_downloaded = []
            try:
                client = sg_sync.DriveClient(str(sg_paths.token_file()))
                if not client.authenticate():
                    return

                                                                                    
                try:
                    self._pull_and_merge_games_json(client)
                except Exception:
                    pass

                for g in sg_manifest.all_games():
                    appid = g.get("appid")
                    save_path = g.get("save_path")
                    if not appid or not save_path or not os.path.isdir(save_path):
                        continue
                    try:
                        info = sg_sync.compare_game(
                            appid, save_path, client, self.steam_path)
                        state = info.get("state")

                                                                      
                        if state == "cloud_newer" and g.get("auto_download"):
                            try:
                                res = sg_sync.sync_game(
                                    appid, save_path, client,
                                    auto_download=True,
                                    steam_path=self.steam_path,
                                    direction="download")
                                if res.get("action") == "downloaded":
                                    now = time.time()
                                    sg_manifest.update_game(
                                        appid,
                                        last_sync=now,
                                        last_download=now,
                                        auto_download=True,
                                    )
                                    name = g.get("name", f"AppID {appid}")
                                    auto_downloaded.append(name)
                                                                       
                                    self._bg_notified[appid] = (
                                        state, info.get("remote_time"))
                                    continue
                            except Exception:
                                pass

                        if state not in ("cloud_newer", "conflict"):
                            continue
                                                                 
                        key = (state, info.get("remote_time"))
                        if self._bg_notified.get(appid) == key:
                            continue
                        self._bg_notified[appid] = key
                        name = g.get("name", f"AppID {appid}")
                        (newer_games if state == "cloud_newer"
                         else conflict_games).append(name)
                    except Exception:
                        continue
            except Exception:
                pass
            finally:
                self._bg_running = False

                                                                      
            if auto_downloaded:
                try:
                    self._push_games_json()
                except Exception:
                    pass

            def shorten(names):
                shown = ", ".join(names[:3])
                if len(names) > 3:
                    shown += f" +{len(names) - 3} more"
                return shown

            if auto_downloaded and not self.silence_warnings:
                self._ui(lambda: _show_toast(
                    "Save Sync",
                    f"Auto-downloaded {len(auto_downloaded)} game(s)",
                    shorten(auto_downloaded),
                    duration_ms=7000, parent=self,
                ))

            lines = []
            if newer_games:
                lines.append(f"Newer on Google Drive: {shorten(newer_games)}")
            if conflict_games:
                lines.append(f"Changed on both sides: {shorten(conflict_games)}")

            if lines and not self.silence_warnings:
                self._ui(lambda: _show_toast(
                    "Save Sync",
                    lines[0],
                    lines[1] if len(lines) > 1 else "",
                    duration_ms=7000, warn=True, parent=self,
                ))

        threading.Thread(target=worker, daemon=True).start()


                                                                                
def main(argv=None):
    parser = argparse.ArgumentParser(description="Save Sync GUI")
    parser.add_argument("--background", action="store_true",
                        help="Start hidden and check for newer cloud saves periodically")
    args = parser.parse_args(argv)

                                                                              
                                                                              
                                 
    if args.background and not sg_paths.acquire_background_lock():
        return

    app = SaveSyncApp(background=args.background)
    app.mainloop()


if __name__ == "__main__":
    main()