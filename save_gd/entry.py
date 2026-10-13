import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from savegd_core.manifest import detect_steam_path
steam_path = detect_steam_path()
                                                                        
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from savegd_core import manifest, sync
from savegd_core.paths import oauth_client_file, token_file, assets_dir


LOG_FILE = Path(os.environ.get("TEMP", ".")) / "save_gd.log"


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _ensure_oauth_client() -> bool:
    runtime_file = oauth_client_file()
    if runtime_file.exists():
        return True

    src = assets_dir() / "oauth_client.json"
    if not src.exists():
        log(f"oauth_client.json not found in assets: {src}")
        print(f"ERROR: oauth_client.json is missing from {assets_dir()}")
        return False

    try:
        runtime_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, runtime_file)
        log(f"Copied oauth_client.json: {src} -> {runtime_file}")
        return True
    except Exception as e:
        log(f"Failed to copy oauth_client.json: {e}")
        print(f"Failed to copy oauth_client.json: {e}")
        return False


def wait_for_exit(exe_name: str, timeout: int = 86400):
    end = time.time() + timeout
    while time.time() < end:
        try:
            out = subprocess.check_output(
                ["tasklist", "/FO", "CSV", "/NH"],
                creationflags=subprocess.CREATE_NO_WINDOW,
            ).decode(errors="ignore").lower()
            if f'"{exe_name.lower()}"' not in out:
                return
        except Exception:
            pass
        time.sleep(2)


def find_marker(game_exe: Path):
    m = game_exe.parent / ".steam_lookup_save_gd.json"
    if not m.exists():
        return None
    try:
        return json.loads(m.read_text(encoding="utf-8"))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--game-exe", default="")
    args = ap.parse_args()

                                                                        
    if args.setup:
        if not _ensure_oauth_client():
            sys.exit(1)
        from save_gd.oauth import run_setup_flow
        ok = run_setup_flow()
        sys.exit(0 if ok else 1)

                                                                        
    if not args.game_exe:
        log("No --game-exe given, nothing to do.")
        return

    game_exe = Path(args.game_exe)
    if not game_exe.exists():
        log(f"Game exe not found: {game_exe}")
        return

    marker = find_marker(game_exe)
    if not marker:
        log(f"No marker next to {game_exe.name}, skipping.")
        return

    appid = marker.get("appid")
    log(f"Tracking AppID {appid} ({marker.get('name')})")
    log(f"Waiting for {game_exe.name} to exit...")

    wait_for_exit(game_exe.name)
    log("Game exited. Syncing...")

    _ensure_oauth_client()

    client = sync.DriveClient(str(token_file()))
    if not client.authenticate():
        log("No valid token; skipping sync. Run save_gd.exe --setup first.")
        return

    entry = manifest.get_game(appid)
    if not entry or not entry.get("save_path"):
        log(f"No save_path for AppID {appid}, skipping.")
        return

    result = sync.sync_game(
        appid,
        entry["save_path"],
        client,
        entry.get("auto_download", False),
    )
    log(f"Sync result: {result['action']} — {result['message']}")

    manifest.update_game(
        appid,
        last_sync=time.time(),
        last_upload=time.time() if result["action"] == "uploaded" else entry.get("last_upload"),
        last_download=time.time() if result["action"] == "downloaded" else entry.get("last_download"),
    )

    if result["action"] in ("uploaded", "downloaded"):
        try:
            from savegd_core.toast import show_toast
            name = entry.get("name") or f"AppID {appid}"
            direction = ("Uploaded to Drive"
                         if result["action"] == "uploaded"
                         else "Downloaded from Drive")
            show_toast(
                title="Save Sync",
                line1=f"{direction}: {name}",
                line2=result.get("message", ""),
                duration_ms=4000,
            )
        except Exception as e:
            log(f"Toast failed: {e}")


if __name__ == "__main__":
    main()