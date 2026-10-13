"""
steam_handler.py — OpenSteamTool bypass handler (with proxy disarm/restore).

Invoked by the proxy DLL (dwmapi.dll etc.) when a game loads. Sequence:
  1. Wait a beat so Steam has fully launched the game.
  2. Gracefully shut Steam down. Steam kills the game as a side effect.
  3. Wait for Steam + game to actually be gone.
  4. Rename OpenSteamTool.dll -> .disabled.
  5. Disarm the proxy DLL (rename dwmapi.dll -> .disabled) so the relaunched game
     doesn't spawn another handler.
  6. Relaunch Steam silently.
  7. Wait for Steam to be up.
  8. Relaunch the game directly.
  9. Wait for the game to exit.
 10. Restore OpenSteamTool.dll AND the proxy DLL.
 11. Optionally restart Steam.
"""

import os
import sys
import time
import argparse
import subprocess
from pathlib import Path

LOG_PATH = Path(os.environ.get("TEMP", ".")) / "steam_handler.log"

PROXY_NAMES = ["dwmapi.dll", "xinput1_4.dll", "version.dll", "dxgi.dll", "d3d11.dll"]


def log(msg: str):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        print(line)
    except Exception:
        pass


def is_running(name: str) -> bool:
    """Case-insensitive check whether a process with this image name is running.
    Uses tasklist CSV output because the default table format truncates names
    longer than 25 characters."""
    name_lower = name.lower()
    try:
        out = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).decode(errors="ignore").lower()
        # CSV rows: "process.exe","1234","Console","1","12,345 K"
        return f'"{name_lower}"' in out
    except Exception:
        return False


def wait_exit(name: str, timeout: int = 60, poll: float = 0.5) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if not is_running(name):
            return True
        time.sleep(poll)
    return False


def wait_start(name: str, timeout: int = 60, poll: float = 0.5) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if is_running(name):
            return True
        time.sleep(poll)
    return False


# ── OpenSteamTool ─────────────────────────────────────────────────────────

def find_ost(steam_root: Path):
    for p in steam_root.rglob("OpenSteamTool.dll"):
        return p
    return None


def find_ost_disabled(steam_root: Path):
    for p in steam_root.rglob("OpenSteamTool.dll.disabled"):
        return p
    return None


def disable_ost(steam_root: Path) -> bool:
    dll = find_ost(steam_root)
    if not dll:
        if find_ost_disabled(steam_root):
            log("OST is already disabled.")
            return True
        log("OpenSteamTool.dll not found.")
        return False
    target = dll.with_name("OpenSteamTool.dll.disabled")
    if target.exists():
        log(f"OST target already exists: {target}")
        return True
    try:
        dll.rename(target)
        log(f"Disabled OST: {dll} -> {target}")
        return True
    except Exception as e:
        log(f"Failed to rename OST: {e}")
        return False


def enable_ost(steam_root: Path) -> bool:
    dis = find_ost_disabled(steam_root)
    if not dis:
        log("No disabled OST to restore.")
        return False
    target = dis.with_name("OpenSteamTool.dll")
    if target.exists():
        log(f"Cannot restore OST — target exists: {target}")
        return False
    try:
        dis.rename(target)
        log(f"Restored OST: {dis} -> {target}")
        return True
    except Exception as e:
        log(f"Failed to restore OST: {e}")
        return False


# ── Proxy DLL disarm/restore ──────────────────────────────────────────────

def find_proxy(game_dir: Path):
    for name in PROXY_NAMES:
        p = game_dir / name
        if p.exists():
            return p
    return None


def disarm_proxy(game_dir: Path):
    proxy = find_proxy(game_dir)
    if not proxy:
        log("No proxy DLL found to disarm (already disarmed?).")
        return None
    target = proxy.with_name(proxy.name + ".disabled")
    if target.exists():
        log(f"Proxy target already exists: {target}")
        return proxy
    try:
        proxy.rename(target)
        log(f"Disarmed proxy: {proxy.name} -> {target.name}")
        return proxy
    except Exception as e:
        log(f"Failed to disarm proxy: {e}")
        return None


def restore_proxy(game_dir: Path):
    for name in PROXY_NAMES:
        dis = game_dir / (name + ".disabled")
        if dis.exists():
            target = game_dir / name
            if target.exists():
                log(f"Cannot restore proxy — target exists: {target}")
                return
            try:
                dis.rename(target)
                log(f"Restored proxy: {dis.name} -> {target.name}")
                return
            except Exception as e:
                log(f"Failed to restore proxy: {e}")
                return
    log("No disarmed proxy found to restore.")


# ── Steam ─────────────────────────────────────────────────────────────────

def shutdown_steam(steam_root: Path, also_kill: str = None):
    steam_exe = steam_root / "steam.exe"
    if not is_running("steam.exe"):
        log("Steam is not running.")
    else:
        log("Asking Steam to shut down (-shutdown)...")
        try:
            subprocess.run(
                [str(steam_exe), "-shutdown"],
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception as e:
            log(f"Graceful shutdown error: {e}")

        if not wait_exit("steam.exe", timeout=30):
            log("Steam didn't exit gracefully — forcing taskkill...")
            subprocess.run(
                ["taskkill", "/F", "/IM", "steam.exe"],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            wait_exit("steam.exe", timeout=10)
        log("Steam is down.")

    if also_kill and is_running(also_kill):
        log(f"Killing leftover {also_kill}...")
        subprocess.run(
            ["taskkill", "/F", "/IM", also_kill],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        wait_exit(also_kill, timeout=10)


def launch_steam(steam_root: Path):
    steam_exe = steam_root / "steam.exe"
    log("Launching Steam silently...")
    subprocess.Popen(
        [str(steam_exe), "-silent"],
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        close_fds=True,
    )


def launch_game(game_exe: Path):
    log(f"Launching game: {game_exe}")
    subprocess.Popen(
        [str(game_exe)],
        cwd=str(game_exe.parent),
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        close_fds=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-exe", required=True)
    ap.add_argument("--steam-path", default=r"C:\Program Files (x86)\Steam")
    ap.add_argument("--detach", action="store_true")
    ap.add_argument("--keep-ost-off", action="store_true")
    ap.add_argument("--no-restart", action="store_true")
    ap.add_argument("--startup-delay", type=float, default=2.0)
    ap.add_argument("--steam-ready-wait", type=float, default=10.0)
    args = ap.parse_args()

    steam_root = Path(args.steam_path)
    game_exe = Path(args.game_exe)
    game_dir = game_exe.parent
    game_name = game_exe.name

    if not (steam_root / "steam.exe").exists():
        log(f"ERROR: steam.exe not found at {steam_root}")
        sys.exit(1)
    if not game_exe.exists():
        log(f"ERROR: game exe not found at {game_exe}")
        sys.exit(1)

    log("=" * 60)
    log(f"Handler started for: {game_name}")
    log(f"Steam root: {steam_root}")
    log(f"Game dir:   {game_dir}")

    # 0. Brief delay so the game is fully visible.
    time.sleep(args.startup_delay)

    # 1. Shut Steam down.
    log("Step 1: shutting Steam down...")
    shutdown_steam(steam_root, also_kill=game_name)

    # 2. Disable OST.
    log("Step 2: disabling OpenSteamTool...")
    ost_disabled = disable_ost(steam_root)

    # 3. Disarm the proxy DLL so the relaunched game doesn't spawn another handler.
    log("Step 3: disarming proxy DLL...")
    proxy_disarmed = disarm_proxy(game_dir)

    # 4. Relaunch Steam.
    log("Step 4: relaunching Steam...")
    launch_steam(steam_root)
    if not wait_start("steam.exe", timeout=60):
        log("ERROR: Steam failed to start. Aborting.")
        if ost_disabled and not args.keep_ost_off:
            enable_ost(steam_root)
        restore_proxy(game_dir)
        sys.exit(1)
    log("Steam is running.")

    # 5. Let Steam settle.
    log(f"Step 5: waiting {args.steam_ready_wait:.0f}s for Steam to settle...")
    time.sleep(args.steam_ready_wait)

    # 6. Relaunch the game.
    log("Step 6: relaunching the game...")
    launch_game(game_exe)

    if not wait_start(game_name, timeout=120):
        log(f"WARNING: {game_name} didn't start. Leaving OST disabled and proxy disarmed.")
        sys.exit(0)

    log(f"{game_name} is running. Waiting for exit...")
    wait_exit(game_name, timeout=24 * 3600)
    log(f"{game_name} exited.")

    # 7. Restore OST.
    if ost_disabled and not args.keep_ost_off:
        log("Step 7: restoring OpenSteamTool...")
        enable_ost(steam_root)

    # 8. Restore proxy.
    log("Step 8: restoring proxy DLL...")
    restore_proxy(game_dir)

    # 9. Optionally restart Steam.
    if not args.no_restart:
        log("Step 9: restarting Steam...")
        shutdown_steam(steam_root)
        launch_steam(steam_root)

    log("Handler done.")
    log("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"UNHANDLED EXCEPTION: {e}")
        import traceback
        log(traceback.format_exc())
        raise