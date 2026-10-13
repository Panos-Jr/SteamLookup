import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


APP_NAME        = "SteamLookup"
RUNTIME_VERSION = "v1.9.1"

                                                           
_RUNTIME_FILES = (
    "save_gd.exe",
    "save_gd_gui.exe",
    "oauth_client.json",
)

_STATE_FILES = (
    "save_gd_manifest.json",
    "games.json",
    "save_gd_silence_warnings.json",
)


def _resolve_assets_dir() -> Path:
    _BASE_DIR = (
    os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)
    if (Path(_BASE_DIR) / "steam_lookup_assets").is_dir():
        return Path(_BASE_DIR) / "steam_lookup_assets"
    return Path(_BASE_DIR)

def runtime_dir() -> Path:
                                                            
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    p = Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def version_marker_dir() -> Path:
                                                                           
    return runtime_dir() / RUNTIME_VERSION


def save_gd_exe() -> Path:
    return runtime_dir() / "save_gd.exe"


def save_gd_gui_exe() -> Path:
    return runtime_dir() / "save_gd_gui.exe"


def oauth_client_file() -> Path:
    return runtime_dir() / "oauth_client.json"


def token_file() -> Path:
    return runtime_dir() / "token.json"


def manifest_file() -> Path:
    return runtime_dir() / "save_gd_manifest.json"


def games_json_file() -> Path:
    return runtime_dir() / "games.json"


def silence_warnings_file() -> Path:
    return runtime_dir() / "save_gd_silence_warnings.json"


def background_lock_file() -> Path:
    return runtime_dir() / "save_gd_gui_background.lock"


def startup_shortcut_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    startup = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup / "SteamLookup Save Sync.lnk"


def assets_dir() -> Path:
    return _resolve_assets_dir()

_bg_lock_handle = None                                         


def acquire_background_lock() -> bool:
    global _bg_lock_handle
    if _bg_lock_handle is not None:
        return True
    try:
        fh = open(background_lock_file(), "a+")
    except OSError:
        return True

    try:
        fh.seek(0, os.SEEK_END)
        if fh.tell() == 0:
            fh.write(" ")
            fh.flush()
        fh.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        try: fh.close()
        except Exception: pass
        return False
    except Exception:
        try: fh.close()
        except Exception: pass
        return True

    _bg_lock_handle = fh
    return True


                                                                                

def _replace_file(src: Path, dst: Path):
    old = dst.with_name(dst.name + ".old")
    moved = False
    if dst.exists():
        try:
            if old.exists():
                old.unlink()
        except Exception:
            pass
        try:
            dst.rename(old)
            moved = True
        except Exception:
            pass                                                              

    try:
        shutil.copy(src, dst)
    except Exception:
        if moved and not dst.exists():
            try: old.rename(dst)                                                   
            except Exception: pass
        raise


def _copy_asset(name: str, dst_dir: Path) -> tuple:
    src = assets_dir() / name
    dst = dst_dir / name
    if not src.exists():
        return False, f"Missing asset: {name} (looked in {src})"
    try:
        _replace_file(src, dst)
        return True, ""
    except Exception as e:
        return False, f"Failed to copy {name}: {e}"


def _sweep_old_files():
    rt = runtime_dir()
    for name in _RUNTIME_FILES:
        p = rt / (name + ".old")
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass                                                               


def _reset_state_files():
    rt = runtime_dir()
    for name in _STATE_FILES:
        p = rt / name
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass


def ensure_runtime_ready() -> tuple:
    rt = runtime_dir()
    marker = version_marker_dir()

    _sweep_old_files()

    if not marker.exists():
        _reset_state_files()

        missing = []
        for name in _RUNTIME_FILES:
            ok, msg = _copy_asset(name, rt)
            if not ok:
                missing.append(msg)

        if missing:
            return False, (
                "Cannot prepare runtime folder.\n\n" +
                "\n".join(missing) +
                f"\n\nAssets folder:\n{assets_dir()}"
            )

        try:
            marker.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return False, f"Failed to create version marker: {e}"
    mf = manifest_file()
    if not mf.exists():
        try:
            mf.write_text(
                '{"version": 1, "drive_root": "SteamLookup_Saves", "games": {}}',
                encoding="utf-8",
            )
        except Exception as e:
            return False, f"Failed to create manifest: {e}"

    cleanup_old_markers()
    return True, str(rt)


def cleanup_old_markers():
    rt = runtime_dir()
    keep = RUNTIME_VERSION
    try:
        for child in rt.iterdir():
            if not child.is_dir():
                continue
            if child.name == keep:
                continue
            if child.name.startswith("v") and len(child.name) <= 6:
                try:
                    child.rmdir()
                except OSError:
                    pass
    except Exception:
        pass

def load_silence_warnings() -> bool:
    try:
        with open(silence_warnings_file()) as f:
            return bool(json.load(f).get("silent", False))
    except Exception:
        return False


def save_silence_warnings(silent: bool):
    try:
        with open(silence_warnings_file(), "w") as f:
            json.dump({"silent": bool(silent)}, f)
    except Exception:
        pass


                 

def _ps_quote(value) -> str:
    return str(value).replace("'", "''")


def is_startup_enabled() -> bool:
    try:
        return startup_shortcut_path().exists()
    except Exception:
        return False


def enable_startup() -> tuple:
    exe = save_gd_gui_exe()
    if not exe.exists():
        return False, (
            f"save_gd_gui.exe not found at:\n{exe}\n\n"
            "Launch SteamLookup first so the runtime folder gets populated."
        )

    lnk = startup_shortcut_path()
    try:
        lnk.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return False, f"Cannot create Startup folder: {e}"

    ps_script = (
        "$ws = New-Object -ComObject WScript.Shell;"
        f"$sc = $ws.CreateShortcut('{_ps_quote(lnk)}');"
        f"$sc.TargetPath = '{_ps_quote(exe)}';"
        "$sc.Arguments = '--background';"
        f"$sc.WorkingDirectory = '{_ps_quote(exe.parent)}';"
        "$sc.WindowStyle = 7;"
        "$sc.Description = 'SteamLookup Save Sync';"
        "$sc.Save();"
    )

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", ps_script],
            capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            return False, f"PowerShell error: {result.stderr.strip()[:300]}"
        if not lnk.exists():
            return False, "Shortcut was not created."
        return True, f"Startup shortcut created:\n{lnk}"
    except Exception as e:
        return False, f"Failed to create shortcut: {e}"


def disable_startup() -> tuple:
    lnk = startup_shortcut_path()
    try:
        if lnk.exists():
            lnk.unlink()
            return True, "Startup shortcut removed."
        return True, "Startup shortcut was not present."
    except Exception as e:
        return False, f"Failed to remove shortcut: {e}"