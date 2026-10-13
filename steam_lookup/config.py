import os
import json
import sys
from pathlib import Path

VERSION = "v1.9.1"

                                                                                
HUBCAP_CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".steam_lookup_hubcap.json")
STEAM_CONFIG_FILE  = os.path.join(os.path.expanduser("~"), ".steam_lookup_steam_path.json")
_REMINDER_FILE     = os.path.join(os.path.expanduser("~"), ".steam_lookup_reminder.json")

                                                                          
_BASE_DIR = Path(
    os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)

if (_BASE_DIR.parent / "steam_lookup_assets").is_dir():
    _BASE_DIR = _BASE_DIR.parent


ASSETS_DIR = str(_BASE_DIR / "steam_lookup_assets")
                                                                                
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

COL_FOUND         = "#81c784"
COL_NOTFOUND      = "#4b5563"
COL_LOADING       = "#4b5563"
COL_ERROR         = "#4b5563"
COL_ALWAYS_ONLINE = "#ce93d8"
COL_ANTICHEAT     = "#ffb74d"

                                                                                
TOGGLE_ON  = "#4ade80"
TOGGLE_OFF = "#3a3f4a"

                                                                                
DRM_META = {
    "denuvo":        ("#ef5350", "🛡",  0),
    "always_online": ("#ce93d8", "🌐",  1),
    "thirdparty":    ("#ffb74d", "⚠",   2),
    "steamworks":    ("#4fc3f7", "🔒",  3),
    "none":          ("#81c784", "✅",  4),
    "unknown":       ("#9ca3af", "❓",  5),
    "loading":       ("#4b5563", "⏳",  9),
}

THIRD_PARTY_KW = [
    ("ea app",                  "EA App"),
    ("ea link",                 "EA Link"),
    ("origin",                  "Origin"),
    ("uplay",                   "Uplay"),
    ("ubisoft connect",         "Ubisoft Connect"),
    ("epic online services",    "Epic Online Services"),
    ("epic games launcher",     "Epic Games Launcher"),
    ("rockstar games launcher", "Rockstar Games Launcher"),
    ("rockstar social club",    "Rockstar Social Club"),
    ("games for windows",       "Games for Windows Live"),
    ("gfwl",                    "Games for Windows Live"),
    ("battle.net",              "Battle.net"),
    ("battlenet",               "Battle.net"),
    ("xbox app",                "Xbox App"),
    ("microsoft store",         "Microsoft Store"),
    ("securom",                 "SecuROM"),
    ("safedisc",                "SafeDisc"),
    ("starforce",               "StarForce"),
    ("tages",                   "TAGES"),
    ("arxan",                   "Arxan"),
    ("vmprotect",               "VMProtect"),
    ("themida",                 "Themida"),
    ("solidshield",             "SolidShield"),
    ("protect disc",            "Protect Disc"),
    ("fade",                    "FADE"),
]

                                                                                
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/json,*/*",
}

PCGW = "https://www.pcgamingwiki.com/w/api.php"

                                                                                
MANUAL_SEARCH_OVERRIDES = {
    "TramSim Vienna": "TramSim Vienna",
    "TramSim Munich": "TramSim Munich",
}

                                                                                
DOWNLOAD_SITES = [
    {"name": "GOG Games ⭐",       "url": "https://gog-games.to",        "query_url": "https://gog-games.to/?search="},
    {"name": "Online-Fix ⭐",      "url": "https://online-fix.me",       "query_url": "https://online-fix.me/index.php?do=search&subaction=search&story=",  "requires_selenium": True},
    {"name": "SteamRIP ⭐",        "url": "https://steamrip.com",        "query_url": "https://steamrip.com/?s=",                                            "requires_selenium": True},
    {"name": "FitGirl Repacks ⭐", "url": "https://fitgirl-repacks.site","query_url": "https://fitgirl-repacks.site/?s="},
    {"name": "Dodi Repacks ⭐",    "url": "https://dodi-repacks.site",   "query_url": "https://dodi-repacks.site/?s=",                                       "requires_selenium": True},
    {"name": "Vimm's Lair ⭐",     "url": "https://vimm.net",            "query_url": "https://vimm.net/vault/?p=list&q="},
    {"name": "Ova Games",          "url": "https://ovagames.com",        "query_url": "https://ovagames.com/?s="},
    {"name": "ElEnemigos",         "url": "https://elenemigos.com",      "query_url": "https://elenemigos.com/?g_name="},
    {"name": "GameDrive",          "url": "https://gamedrive.org",       "query_url": "https://gamedrive.org/?s="},
    {"name": "GAMESPACK",          "url": "https://gamespack.net",       "query_url": "https://gamespack.net/?s="},
    {"name": "GLOAD",              "url": "https://gload.to",            "query_url": "https://gload.to/?s="},
    {"name": "Games 4 U",          "url": "https://g4u.to",              "query_url": "https://g4u.to/en/search/"},
    {"name": "Games4U",            "url": "https://games4u.org",         "query_url": "https://games4u.org/?s="},
    {"name": "Gamdie",             "url": "https://gamdie.com",          "query_url": "https://gamdie.com/?s="},
    {"name": "AnkerGames",         "url": "https://ankergames.net",      "query_url": "https://ankergames.net/search/"},
    {"name": "Rom Hustler",        "url": "https://romhustler.org",      "query_url": "https://romhustler.org/roms/search?query="},
    {"name": "Romulation",         "url": "https://www.romulation.org",  "query_url": "https://www.romulation.org/roms/search?query="},
    {"name": "Blueroms",           "url": "https://www.blueroms.ws",     "query_url": "https://www.blueroms.ws/search?g=0&p=0&q="},
    {"name": "Romspure",           "url": "https://romspure.cc",         "query_url": "https://romspure.cc/?s="},
    {"name": "Nxbrew",             "url": "https://nxbrew.net",          "query_url": "https://nxbrew.net/?s="},
    {"name": "EpicRoms",           "url": "https://epicroms.net",        "query_url": "https://epicroms.net/?s="},
    {"name": "Abandonware Games",  "url": "https://abandonwaregames.net","query_url": "https://abandonwaregames.net/search.php?q="},
    {"name": "My Abandonware",     "url": "https://www.myabandonware.com","query_url": "https://www.myabandonware.com/search/q/"},
    {"name": "Old Games Download", "url": "https://oldgamesdownload.com","query_url": "https://oldgamesdownload.com/search/?s="},
    {"name": "Old-Games.RU",       "url": "https://www.old-games.ru",    "query_url": "https://www.old-games.ru/catalog/?gamename="},
]

ONLINE_FIX_SITE = {
    "name": "Online-Fix ⭐",
    "url": "https://online-fix.me",
    "query_url": "https://online-fix.me/index.php?do=search&subaction=search&story=",
    "requires_selenium": True,
}

                                                                                

def load_hubcap_key() -> str:
    try:
        with open(HUBCAP_CONFIG_FILE) as f:
            return json.load(f).get("api_key", "")
    except Exception:
        return ""


def save_hubcap_key(key: str):
    try:
        with open(HUBCAP_CONFIG_FILE, "w") as f:
            json.dump({"api_key": key}, f)
    except Exception:
        pass


def load_steam_path() -> str:
    try:
        with open(STEAM_CONFIG_FILE) as f:
            p = json.load(f).get("path", "")
            if p and os.path.exists(p):
                return p
    except Exception:
        pass
    default = r"C:\Program Files (x86)\Steam"
    return default if os.path.exists(default) else ""


def save_steam_path(path: str):
    try:
        with open(STEAM_CONFIG_FILE, "w") as f:
            json.dump({"path": path}, f)
    except Exception:
        pass


def load_reminder_state() -> bool:
    try:
        with open(_REMINDER_FILE) as f:
            return json.load(f).get("disabled", False)
    except Exception:
        return False


def save_reminder_state(disabled: bool):
    try:
        with open(_REMINDER_FILE, "w") as f:
            json.dump({"disabled": disabled}, f)
    except Exception:
        pass