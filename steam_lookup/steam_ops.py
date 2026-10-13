import os
import re
import time
import subprocess
from pathlib import Path
import shutil
from .config import ASSETS_DIR

                                                            
PROXY_NAMES = ["dwmapi.dll", "xinput1_4.dll", "version.dll", "dxgi.dll", "d3d11.dll"]


                                                                                
def _is_steam_running() -> bool:
    try:
        out = subprocess.check_output(
            "tasklist /FI \"IMAGENAME eq steam.exe\"", shell=True
        ).decode(errors="ignore")
        return "steam.exe" in out.lower()
    except Exception:
        return False


def restart_steam(steam_path: str) -> str:
                                                                        
    steam_root = Path(steam_path or r"C:\Program Files (x86)\Steam")
    steam_exe  = steam_root / "steam.exe"
    was_running = _is_steam_running()

    if was_running and steam_exe.exists():
        try:
            subprocess.run([str(steam_exe), "-shutdown"], check=True, timeout=10)
            time.sleep(3)
            if _is_steam_running():
                subprocess.run(["taskkill", "/F", "/IM", "steam.exe"],
                               capture_output=True, check=False)
                time.sleep(1)
        except Exception as e:
            return f"❌ Failed to shut down Steam: {e}"

    try:
        if steam_exe.exists():
            os.startfile(str(steam_exe))
            return "🔄 Steam restarted gracefully." if was_running else "🔄 Steam launched."
        os.startfile("steam://open/games")
        return "🔄 Steam launched via URI (fallback)."
    except Exception:
        try:
            os.startfile("steam://open/games")
            return "🔄 Steam launched via URI (fallback)."
        except Exception as e2:
            return f"❌ Failed to launch Steam: {e2}"


                                                                                
def remove_game_files(steam_path: str, appid: int, log_fn) -> int:
\
                                                                  
    steam_root = Path(steam_path or r"C:\Program Files (x86)\Steam")
    if not steam_root.exists():
        log_fn("❌ Steam folder not found.\n", "red")
        return 0

    paths = {
        "stplugin":          steam_root / "config" / "stplug-in",
        "config_depotcache": steam_root / "config" / "depotcache",
        "depotcache":        steam_root / "depotcache",
        "stui":              steam_root / "config" / "stUI",
        "stats":             steam_root / "config" / "StatsExport",
        "lua":               steam_root / "config" / "lua",
    }

    game_id_str = str(appid)
    if len(game_id_str) < 2:
        log_fn("❌ AppID too short.\n", "red")
        return 0
    pattern = rf"{game_id_str[0:-1]}\d\D+"

    file_count = 0
    for path_key, path in paths.items():
        if not path.exists():
            continue
        try:
            entries = os.listdir(path)
        except Exception as e:
            log_fn(f"❌ Cannot read {path}: {e}\n", "red")
            continue
        for fname in entries:
            if path_key == "stats":
                match = f"_{game_id_str}_" in fname
            else:
                match = re.match(pattern, fname)
            if match and fname:
                try:
                    full_path = path / fname
                    log_fn(f"{full_path}\n", "cyan")
                    os.remove(full_path)
                    file_count += 1
                except Exception as e:
                    log_fn(f"Error deleting {full_path}: {e}\n", "red")
    return file_count


                                                                                
def find_asset(name: str) -> str:
                                                                         
    p = Path(ASSETS_DIR) / name
    return str(p) if p.exists() else ""


                                                                                
def find_game_exe(folder: Path):
                                                             
    for pat in ("*-Win64-Shipping.exe", "*Shipping.exe", "*-Win32-Shipping.exe"):
        hits = list(folder.rglob(pat))
        if hits:
            return hits[0]
    skip = {"steam_handler.exe", "steam.exe", "launcher.exe"}
    for p in folder.rglob("*.exe"):
        if p.name.lower() not in skip:
            return p
    return None


                                                                                
CLOUD_DLL_NAME = "cloud_redirect.dll"
CLOUD_EXE_NAME = "CloudRedirect.exe"


def setup_cloud_redirect(steam_path: str, on_status=None):
\
\
\
\
\
\
\
\
       
    def status(text, color=TEXT_MUTED if False else None):
        if on_status:
            try:
                on_status(text, color)
            except Exception:
                pass

    steam_root = Path(steam_path or r"C:\Program Files (x86)\Steam")
    if not steam_root.exists():
        return False, f"Steam folder not found:\n{steam_root}"

    src_dll = Path(ASSETS_DIR) / CLOUD_DLL_NAME
    src_exe = Path(ASSETS_DIR) / CLOUD_EXE_NAME

    if not src_dll.exists():
        return False, (
            f"{CLOUD_DLL_NAME} not found in assets:\n{ASSETS_DIR}\n\n"
            "Place it there first."
        )
    if not src_exe.exists():
        return False, (
            f"{CLOUD_EXE_NAME} not found in assets:\n{ASSETS_DIR}\n\n"
            "Place it there first."
        )

    dst_dll = steam_root / CLOUD_DLL_NAME

                                                                          
    status("Copying cloud_redirect.dll into Steam…")
    try:
        if dst_dll.exists():
            dst_dll.unlink()
        shutil.copy(src_dll, dst_dll)
    except PermissionError:
        return False, (
            f"Permission denied writing to:\n{dst_dll}\n\n"
            "Close Steam fully and try again."
        )
    except Exception as e:
        return False, f"Failed to copy {CLOUD_DLL_NAME}: {e}"

                                                                         
    status("Restarting Steam to load the DLL…")
    restart_msg = restart_steam(steam_path)

                                                                         
    status(f"Launching {CLOUD_EXE_NAME}…")
    try:
        subprocess.Popen(
            [str(src_exe)],
            cwd=str(src_exe.parent),
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )
    except Exception as e:
        return False, f"Copied DLL, but failed to launch {CLOUD_EXE_NAME}: {e}"

    return True, (
        f"✅ Installed {CLOUD_DLL_NAME} to:\n{dst_dll}\n\n"
        f"{restart_msg}\n\n"
        f"🚀 Launched {CLOUD_EXE_NAME}."
    )