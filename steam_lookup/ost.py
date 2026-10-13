import json
import time
import shutil
import subprocess
from pathlib import Path
import os
from . import steam_ops


                                                                                
def _ost_find(steam_path: str):
    steam_root = Path(steam_path or r"C:\Program Files (x86)\Steam")
    if not steam_root.exists():
        return None, None
    enabled = None
    disabled = None
    for p in steam_root.rglob("OpenSteamTool.dll"):
        enabled = p
        break
    for p in steam_root.rglob("OpenSteamTool.dll.disabled"):
        disabled = p
        break
    return enabled, disabled


def ost_currently_disabled(steam_path: str) -> bool:
    enabled, disabled = _ost_find(steam_path)
    return disabled is not None and enabled is None


def ost_set_disabled(steam_path: str, disabled: bool) -> bool:
    enabled, dis = _ost_find(steam_path)
    if disabled:
        if dis and not enabled:
            return True
        if not enabled:
            return False
        target = enabled.with_name("OpenSteamTool.dll.disabled")
        try:
            if target.exists():
                target.unlink()
            enabled.rename(target)
            return True
        except Exception:
            return False
    else:
        if enabled and not dis:
            return True
        if not dis:
            return False
        target = dis.with_name("OpenSteamTool.dll")
        try:
            if target.exists():
                target.unlink()
            dis.rename(target)
            return True
        except Exception:
            return False


                                                                                
def deploy_bypass(game_dir: Path):
                                
    if not game_dir.exists():
        return False, f"Folder doesn't exist:\n{game_dir}"

    proxy_src   = steam_ops.find_asset("dwmapi.dll")
    handler_src = steam_ops.find_asset("steam_handler.exe")
    if not proxy_src:
        return False, (
            f"Missing dwmapi.dll.\n"
            f"Place it in:\n{steam_ops.ASSETS_DIR}"
        )
    if not handler_src:
        return False, (
            f"Missing steam_handler.exe.\n"
            f"Place it in:\n{steam_ops.ASSETS_DIR}"
        )

    game_exe = steam_ops.find_game_exe(game_dir)
    if not game_exe:
        return False, f"No .exe found in {game_dir}"

    target_proxy   = game_dir / "dwmapi.dll"
    target_handler = game_dir / "steam_handler.exe"
    meta_file      = game_dir / ".steam_lookup_ost_bypass.json"

    try:
        if target_proxy.exists():
            target_proxy.unlink()
        if target_handler.exists():
            target_handler.unlink()
        shutil.copy(proxy_src, target_proxy)
        shutil.copy(handler_src, target_handler)
        meta_file.write_text(json.dumps({
            "proxy":       "dwmapi.dll",
            "handler":     "steam_handler.exe",
            "game_exe":    game_exe.name,
            "deployed_at": time.time(),
        }, indent=2))
    except Exception as e:
        return False, str(e)

    return True, (
        f"Installed to:\n{game_dir}\n\n"
        f"Proxy:   dwmapi.dll\n"
        f"Handler: steam_handler.exe\n"
        f"Target:  {game_exe.name}\n\n"
        "Next time you launch the game, Steam will be restarted with OST disabled,\n"
        "then the game will be relaunched automatically."
    )


def remove_bypass(game_dir: Path):
                                
    meta = game_dir / ".steam_lookup_ost_bypass.json"
    if not meta.exists():
        removed = []
        for name in steam_ops.PROXY_NAMES + ["steam_handler.exe"]:
            p = game_dir / name
            if p.exists():
                try:
                    p.unlink()
                    removed.append(name)
                except Exception:
                    pass
        if removed:
            return True, f"Removed: {', '.join(removed)}"
        return False, "No .steam_lookup_ost_bypass.json found here."

    try:
        data = json.loads(meta.read_text())
        for f in (data.get("proxy"), data.get("handler")):
            if f:
                p = game_dir / f
                if p.exists():
                    p.unlink()
        for n in steam_ops.PROXY_NAMES + ["steam_handler.exe"]:
            p = game_dir / (n + ".disabled")
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass
        meta.unlink()
        return True, f"OST bypass removed from:\n{game_dir}"
    except Exception as e:
        return False, str(e)


def launch_bypass(game_dir: Path, steam_path: str):
                                                                              
    handler = game_dir / "steam_handler.exe"
    meta    = game_dir / ".steam_lookup_ost_bypass.json"
    if not handler.exists() or not meta.exists():
        return False, (
            "This game doesn't have the OST bypass installed.\n"
            "Use ⋮ → Deploy OST bypass first."
        )
    try:
        data = json.loads(meta.read_text())
        game_exe = game_dir / data["game_exe"]
        if not game_exe.exists():
            found = steam_ops.find_game_exe(game_dir)
            if not found:
                return False, "Couldn't find the game exe."
            game_exe = found
        subprocess.Popen(
            [str(handler),
             "--game-exe", str(game_exe),
             "--steam-path", steam_path or r"C:\Program Files (x86)\Steam",
             "--detach"],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )
        return True, f"🚀 Launched steam_handler for {game_exe.name}"
    except Exception as e:
        return False, str(e)

                                                                               

                                                                               

OST_RELEASE_URL = (
    "https://github.com/OpenSteam001/OpenSteamTool/releases/download/"
    "1.4.8/OpenSteamTool-1.4.8-Release.zip"
)


def apply_ost_release(steam_path: str, on_status=None) -> tuple:
    import io
    import shutil
    import tempfile
    import urllib.request
    import zipfile
    from pathlib import Path

    def status(msg):
        if on_status:
            try:
                on_status(msg)
            except Exception:
                pass

    if not steam_path or not Path(steam_path).is_dir():
        return False, f"Steam folder not found: {steam_path}"

    steam_root = Path(steam_path)

    status("Downloading OpenSteamTool 1.4.8…")
    try:
        req = urllib.request.Request(
            OST_RELEASE_URL,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            blob = r.read()
    except Exception as e:
        return False, f"Download failed:\n{e}"

    if not blob:
        return False, "Download returned an empty file."

    status(f"Downloaded {len(blob):,} bytes. Extracting…")

    tmp_root = Path(tempfile.mkdtemp(prefix="ost_apply_"))
    try:
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                zf.extractall(tmp_root)
        except Exception as e:
            return False, f"Extract failed:\n{e}"

                                                                      
                                                                       
                                                                          
                                                       
        def find_payload_root(base: Path) -> Path:
            for root, _dirs, files in os.walk(base):
                for f in files:
                    if f.lower().endswith(".dll"):
                        return Path(root)
                                                                         
                                      
            return base

        payload = find_payload_root(tmp_root)

                                                                       
        status(f"Copying files into {steam_root}…")
        copied = 0
        skipped = []

        for item in payload.rglob("*"):
            try:
                rel = item.relative_to(payload)
            except ValueError:
                continue
            dest = steam_root / rel

            if item.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue

            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
                copied += 1
            except PermissionError as e:
                skipped.append(f"{rel} (in use: {e})")
            except Exception as e:
                skipped.append(f"{rel} ({e})")

        msg = f"Copied {copied} file(s) into Steam."
        if skipped:
            shown = "\n".join(skipped[:5])
            if len(skipped) > 5:
                shown += f"\n… and {len(skipped) - 5} more"
            msg += (
                "\n\nSome files could not be written (Steam may still be "
                "holding them):\n" + shown +
                "\n\nClose Steam fully and retry if OST doesn't load."
            )

        status("Done.")
        return True, msg
    finally:
        try:
            shutil.rmtree(tmp_root, ignore_errors=True)
        except Exception:
            pass