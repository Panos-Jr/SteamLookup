import re
from pathlib import Path


def _find_library_folders(steam_path: str) -> list:
    steam_path = Path(steam_path or r"C:\Program Files (x86)\Steam")
    libs = [steam_path]

    vdf = steam_path / "steamapps" / "libraryfolders.vdf"
    if not vdf.exists():
        return libs

    try:
        text = vdf.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return libs

    for m in re.finditer(r'"path"\s+"([^"]+)"', text):
        p = Path(m.group(1).replace("\\\\", "\\"))
        if p.exists() and p not in libs:
            libs.append(p)

    return libs


def scan_installed_games(steam_path: str) -> list:
    games = []
    seen = set()

    for lib in _find_library_folders(steam_path):
        apps_dir = lib / "steamapps"
        if not apps_dir.exists():
            continue

        for acf in apps_dir.glob("appmanifest_*.acf"):
            try:
                text = acf.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            appid_m = re.search(r'"appid"\s+"(\d+)"', text)
            name_m  = re.search(r'"name"\s+"([^"]+)"', text)
            dir_m   = re.search(r'"installdir"\s+"([^"]+)"', text)

            if not (appid_m and name_m and dir_m):
                continue

            try:
                appid = int(appid_m.group(1))
            except ValueError:
                continue

            if appid in seen:
                continue
            seen.add(appid)

            install_dir = apps_dir / "common" / dir_m.group(1)
            games.append({
                "appid":      appid,
                "name":       name_m.group(1),
                "installdir": str(install_dir),
                "library":    str(lib),
            })

    games.sort(key=lambda g: g["name"].lower())
    return games


def find_game_folder(appid: int, steam_path: str):
    for g in scan_installed_games(steam_path):
        if g["appid"] == appid:
            return Path(g["installdir"])
    return None