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
   

import glob
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .config import BROWSER_HEADERS, PCGW_API, PCGW_APPID, PCGW_HEADERS
from .paths import manifest_file


STEAMID64_BASE = 76561197960265728


                                                                                

def load_manifest() -> dict:
    mf = manifest_file()
    try:
        with open(mf, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("bad shape")
            data.setdefault("version", 1)
            data.setdefault("drive_root", "SteamLookup_Saves")
            data.setdefault("games", {})
            return data
    except Exception:
        return {"version": 1, "drive_root": "SteamLookup_Saves", "games": {}}


def save_manifest(data: dict):
    mf = manifest_file()
    tmp = str(mf) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, mf)


                                                                                

                                                                      
_TEMPLATE_ENV_KEYS = [
    ("userprofile",       "USERPROFILE"),
    ("localappdata",      "LOCALAPPDATA"),
    ("appdata",           "APPDATA"),
    ("programdata",       "PROGRAMDATA"),
    ("public",            "PUBLIC"),
    ("programfiles(x86)", "PROGRAMFILES(X86)"),
    ("programfiles",      "PROGRAMFILES"),
    ("windir",            "WINDIR"),
]

_TEMPLATE_PATTERN = re.compile(r"\{\{[pP]\|([^}]+)\}\}")


def _abs_to_template(abs_path: str, steam_path: str = "") -> str:
\
\
\
\
\
\
       
    if not abs_path:
        return ""

    p = abs_path.replace("/", "\\")

                                                                                 
    for key, env in sorted(_TEMPLATE_ENV_KEYS, key=lambda x: -len(x[0])):
        val = os.environ.get(env)
        if not val:
            continue
        val_norm = os.path.normpath(val).replace("/", "\\").rstrip("\\")
        if p.lower().startswith(val_norm.lower() + "\\") or p.lower() == val_norm.lower():
            tail = p[len(val_norm):].lstrip("\\")
            return f"{{{{p|{key}}}}}\\{tail}" if tail else f"{{{{p|{key}}}}}"

                
    if steam_path:
        sp = os.path.normpath(steam_path).replace("/", "\\").rstrip("\\")
        if p.lower().startswith(sp.lower() + "\\") or p.lower() == sp.lower():
            tail = p[len(sp):].lstrip("\\")
            return f"{{{{p|steam}}}}\\{tail}" if tail else "{{p|steam}}"

    return abs_path


def _template_to_abs(template: str, appid: int = 0,
                     steam_path: str = "") -> str:
\
\
\
       
    if not template:
        return ""

                                          
    if not _TEMPLATE_PATTERN.search(template):
        return _expand_path(template)

    ph = _build_placeholders(appid, steam_path or "")
    expanded = _expand_placeholders(template, ph)
    return expanded[0] if expanded else ""


def _is_portable_template(s: str) -> bool:
                                                                         
    return bool(s and _TEMPLATE_PATTERN.search(s))


                                                                                

def get_game(appid: int):
    return load_manifest()["games"].get(str(appid))


def is_enrolled(appid: int) -> bool:
    return str(appid) in load_manifest()["games"]


def enroll_and_resolve(appid: int, name: str, steam_path: str) -> dict:
\
\
\
       
    enroll_game(appid, name, steam_path=steam_path)
    path, src = resolve_save_path(appid, steam_path)
    if path:
        tmpl = _abs_to_template(path, steam_path)
        return update_game(
            appid,
            save_path=path,
            save_path_source=src,
            save_path_template=tmpl if _is_portable_template(tmpl) else "",
        )
    return get_game(appid)


def enroll_game(appid: int, name: str, steam_path: str = "",
                save_path: str = "", save_path_source: str = "",
                save_path_template: str = "") -> dict:
    data = load_manifest()
    key  = str(appid)
    existing = data["games"].get(key, {})

    entry = {
        "appid":              appid,
        "name":               name,
        "save_path":          save_path or existing.get("save_path", ""),
        "save_path_template": (save_path_template
                               or existing.get("save_path_template", "")),
        "save_path_source":   save_path_source or existing.get("save_path_source", ""),
        "auto_download":      existing.get("auto_download", False),
        "last_sync":          existing.get("last_sync"),
        "last_upload":        existing.get("last_upload"),
        "last_download":      existing.get("last_download"),
        "enrolled_at":        existing.get("enrolled_at", time.time()),
        "deployed_dirs":      existing.get("deployed_dirs", []),
        "proxy_dirs":         existing.get("proxy_dirs", []),
    }
    data["games"][key] = entry
    save_manifest(data)
    return entry


def unenroll_game(appid: int):
    data = load_manifest()
    data["games"].pop(str(appid), None)
    save_manifest(data)


def update_game(appid: int, **fields):
    data = load_manifest()
    key  = str(appid)
    if key not in data["games"]:
        return None
    data["games"][key].update(fields)
    save_manifest(data)
    return data["games"][key]


def all_games() -> list:
    data = load_manifest()
    return sorted(data["games"].values(), key=lambda g: g.get("name", "").lower())


                                                                                

def _parse_vdf(text: str) -> dict:
                                                                             
    tokens = []
    for m in re.finditer(r'"((?:[^"\\]|\\.)*)"|([{}])', text):
        if m.group(1) is not None:
            tokens.append(("s", m.group(1)))
        else:
            tokens.append(("b", m.group(2)))

    root: dict = {}
    stack = [root]
    i = 0
    while i < len(tokens):
        kind, val = tokens[i]
        if kind == "b":
            if val == "}" and len(stack) > 1:
                stack.pop()
            i += 1
            continue

        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        if nxt and nxt[0] == "b" and nxt[1] == "{":
            child: dict = {}
            stack[-1][val] = child
            stack.append(child)
            i += 2
        elif nxt and nxt[0] == "s":
            stack[-1][val] = nxt[1]
            i += 2
        else:
            i += 1
    return root


def _ci_get(d: dict, key: str, default=None):
                                                                                
    for k, v in d.items():
        if k.lower() == key.lower():
            return v
    return default


def _registry_active_user():
                                                                                    
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Valve\Steam\ActiveProcess") as k:
            value = int(winreg.QueryValueEx(k, "ActiveUser")[0])
            return value or None
    except Exception:
        return None


def _loginusers_active_user(steam_path: str):
    vdf = Path(steam_path) / "config" / "loginusers.vdf"
    if not vdf.exists():
        return None
    try:
        data = _parse_vdf(vdf.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None

    users = _ci_get(data, "users", {})
    best_id, best_ts = None, -1
    for steamid64, info in users.items():
        if not (isinstance(info, dict) and steamid64.isdigit()):
            continue
        if str(_ci_get(info, "MostRecent", "0")) == "1":
            return int(steamid64) - STEAMID64_BASE
        try:
            ts = int(_ci_get(info, "Timestamp", 0))
        except ValueError:
            ts = 0
        if ts > best_ts:                                                   
            best_id, best_ts = steamid64, ts
    return int(best_id) - STEAMID64_BASE if best_id else None


def _userdata_active_user(steam_path: str):
    ud = Path(steam_path) / "userdata"
    if not ud.exists():
        return None
    dirs = [d for d in ud.iterdir() if d.name.isdigit() and d.name != "0"]
    if not dirs:
        return None
    if len(dirs) == 1:
        return int(dirs[0].name)
    return int(max(dirs, key=lambda d: d.stat().st_mtime).name)


def get_active_steamid3(steam_path: str):
\
\
\
\
       
    uid = _registry_active_user()
    if uid:
        return uid
    if not steam_path:
        return None
    return (_loginusers_active_user(steam_path)
            or _userdata_active_user(steam_path))


def _steam_user_ids(steam_path: str) -> list:
    if not steam_path:
        return []
    ud = Path(steam_path) / "userdata"
    if not ud.exists():
        return []
    return [d.name for d in ud.iterdir() if d.name.isdigit() and d.name != "0"]


def _game_install_dir(appid: int, steam_path: str):
                                                                    
    if not steam_path:
        return None
    steam_root = Path(steam_path)
    libs = [steam_root]

    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        try:
            text = vdf.read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(r'"path"\s+"([^"]+)"', text):
                libs.append(Path(m.group(1).replace("\\\\", "\\")))
        except Exception:
            pass

    for lib in libs:
        acf = lib / "steamapps" / f"appmanifest_{appid}.acf"
        if acf.exists():
            try:
                text = acf.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r'"installdir"\s+"([^"]+)"', text)
                if m:
                    return lib / "steamapps" / "common" / m.group(1)
            except Exception:
                pass
    return None


                                                                                

def _pcgw_page_title(appid: int) -> str:
                                                                          
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    url = PCGW_APPID + "?" + urllib.parse.urlencode({"appid": appid})
    req = urllib.request.Request(url, headers=PCGW_HEADERS)

    try:
        opener.open(req, timeout=15)
        return ""
    except urllib.error.HTTPError as e:
        if e.code not in (301, 302, 303, 307, 308):
            return ""
        loc = e.headers.get("Location", "")
    except Exception:
        return ""

    if "/wiki/" not in loc:
        return ""
    return urllib.parse.unquote(loc.rsplit("/wiki/", 1)[1])


def _pcgw_wikitext(title: str) -> str:
    params = {
        "action": "parse", "page": title,
        "prop": "wikitext", "format": "json",
    }
    url = PCGW_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=PCGW_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
        return data.get("parse", {}).get("wikitext", {}).get("*", "")
    except Exception:
        return ""


def _split_template_params(s: str) -> list:
                                                  
    parts, cur, depth, i = [], "", 0, 0
    while i < len(s):
        if s.startswith("{{", i):
            depth += 1
            cur += "{{"
            i += 2
        elif s.startswith("}}", i):
            depth -= 1
            cur += "}}"
            i += 2
        elif s[i] == "|" and depth == 0:
            parts.append(cur)
            cur = ""
            i += 1
        else:
            cur += s[i]
            i += 1
    parts.append(cur)
    return parts


def detect_steam_path() -> str:
                                                                 
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            return os.path.normpath(winreg.QueryValueEx(k, "SteamPath")[0])
    except Exception:
        pass

                                
    candidates = [
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
        r"D:\Steam",
        r"E:\Steam",
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return ""


def _extract_templates(wikitext: str, name: str) -> list:
                                                                           
    out, start = [], 0
    marker = "{{" + name
    while True:
        idx = wikitext.find(marker, start)
        if idx == -1:
            break
        depth, i = 0, idx
        while i < len(wikitext):
            if wikitext.startswith("{{", i):
                depth += 1
                i += 2
            elif wikitext.startswith("}}", i):
                depth -= 1
                i += 2
                if depth == 0:
                    out.append(wikitext[idx + 2:i - 2])
                    break
            else:
                i += 1
        start = max(i, idx + len(marker))
    return out


def _pcgw_save_templates(appid: int) -> dict:
                                                                         
    title = _pcgw_page_title(appid)
    if not title:
        return {}
    wikitext = _pcgw_wikitext(title)
    if not wikitext:
        return {}

    results = {}
    for inner in _extract_templates(wikitext, "Game data/saves"):
        params = _split_template_params(inner)
        if len(params) < 3:
            continue
        system = params[1].strip()
        paths = [p.strip() for p in params[2:] if p.strip()]
        results.setdefault(system, []).extend(paths)
    return results


                                                                                

_PH_RE = re.compile(r"\{\{[pP]\|([^}]+)\}\}")


def _build_placeholders(appid: int, steam_path: str) -> dict:
    env = os.environ.get
    ph = {
        "userprofile":       env("USERPROFILE", ""),
        "appdata":           env("APPDATA", ""),
        "localappdata":      env("LOCALAPPDATA", ""),
        "programdata":       env("PROGRAMDATA", ""),
        "public":            env("PUBLIC", ""),
        "windir":            env("WINDIR", ""),
        "programfiles":      env("PROGRAMFILES", ""),
        "programfiles(x86)": env("PROGRAMFILES(X86)", ""),
        "steam":             steam_path,
    }

    uids = _steam_user_ids(steam_path)
    if uids:
                                                                              
        active = get_active_steamid3(steam_path)
        if active is not None and str(active) in uids:
            uids.remove(str(active))
            uids.insert(0, str(active))
        ph["uid"] = uids

    game_dir = _game_install_dir(appid, steam_path)
    if game_dir:
        ph["game"] = str(game_dir)

    return {k: v for k, v in ph.items() if v}


def _expand_placeholders(path: str, placeholders: dict) -> list:
                                                                         
    ph_lists = {k: (v if isinstance(v, list) else [v])
                for k, v in placeholders.items()}

    candidates = [path]
    while any(_PH_RE.search(c) for c in candidates):
        nxt = []
        for c in candidates:
            m = _PH_RE.search(c)
            if not m:
                nxt.append(c)
                continue
            key, *rest = re.split(r"[\\/]", m.group(1), maxsplit=1)
            values = ph_lists.get(key.strip().lower())
            if not values:
                continue
            tail = ("\\" + rest[0]) if rest else ""
            for v in values:
                nxt.append(c[:m.start()] + v + tail + c[m.end():])
        candidates = nxt

    return [os.path.expandvars(os.path.normpath(c)) for c in candidates]


                                                                          
                                                                       
                                                    
_SECTION_PRIORITY = [
    "windows",
    "steam",
    "gog.com",
    "epic games launcher",
    "microsoft store",
    "microsoft store (pc)",
    "origin",
    "uplay",
    "ubisoft connect",
    "battle.net",
    "itch.io",
    "amazon games",
]


def _rank_save_sections(templates: dict) -> list:
\
\
\
\
\
\
\
\
\
       
    if not templates:
        return []

    priority_index = {name: i for i, name in enumerate(_SECTION_PRIORITY)}

    def sort_key(item):
        name, _paths = item
        return priority_index.get(name.strip().lower(), len(_SECTION_PRIORITY))

    ordered = sorted(templates.items(), key=sort_key)

    ranked = []
    for _name, paths in ordered:
        if paths:
            ranked.extend(paths)
    return ranked


def _pcgw_lookup_save_path(appid: int, steam_path: str = "") -> str:
                                                                     
    templates = _pcgw_save_templates(appid)
    if not templates:
        return ""

    raw_paths = _rank_save_sections(templates)
    if not raw_paths:
        return ""

    placeholders = _build_placeholders(appid, steam_path or "")

    first_expanded = ""
    for raw in raw_paths:
        for expanded in _expand_placeholders(raw, placeholders):
            if not first_expanded:
                first_expanded = expanded
            matches = glob.glob(expanded) if "*" in expanded else [expanded]
            for m in matches:
                if os.path.exists(m):
                    return m

    return first_expanded


def _pcgw_lookup_template(appid: int, steam_path: str = "") -> str:
\
\
\
\
       
    templates = _pcgw_save_templates(appid)
    if not templates:
        return ""

    raw_paths = _rank_save_sections(templates)
    if not raw_paths:
        return ""

    placeholders = _build_placeholders(appid, steam_path or "")
    first_raw = raw_paths[0]

    for raw in raw_paths:
        if not _is_portable_template(raw):
            continue
        for expanded in _expand_placeholders(raw, placeholders):
            matches = glob.glob(expanded) if "*" in expanded else [expanded]
            for m in matches:
                if os.path.exists(m):
                    return raw
    return first_raw


                                                                                

def _expand_path(p: str) -> str:
    if not p:
        return ""
    p = p.strip().strip(   ).strip(   )
    p = re.sub(r"\s*\((Windows|Linux|macOS|OS X)\)\s*$", "", p, flags=re.I)
    p = os.path.expandvars(p)
    p = os.path.expanduser(p)
    p = p.replace("/", os.sep).replace("\\", os.sep)
    return p


def _steam_userdata_path(steam_path: str, appid: int) -> str:
    steamid3 = get_active_steamid3(steam_path)
    if not steamid3:
        return ""
    p = Path(steam_path) / "userdata" / str(steamid3) / str(appid) / "remote"
    return str(p) if p.exists() else ""


def _is_steam_userdata_path(p: str, steam_path: str) -> bool:
                                                           
    if not p or not steam_path:
        return False
    try:
        norm = os.path.normpath(p).lower()
        ud   = os.path.normpath(str(Path(steam_path) / "userdata")).lower()
        return norm == ud or norm.startswith(ud + os.sep)
    except Exception:
        return False


def _pcgw_lookup_save_path_and_template(appid: int, steam_path: str) -> tuple:
\
\
\
\
       
    tmpl = _pcgw_lookup_template(appid, steam_path)
    path = _pcgw_lookup_save_path(appid, steam_path)
    return path, tmpl


def resolve_save_path(appid: int, steam_path: str) -> tuple:
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
       
    entry = get_game(appid) or {}

                                                           
    tmpl = entry.get("save_path_template") or ""
    if tmpl:
        local = _template_to_abs(tmpl, appid, steam_path)
        if local:
            if local != entry.get("save_path"):
                update_game(appid, save_path=local)
            return local, "template"

                                                                            
                                                                            
                                                                   
    cached     = entry.get("save_path") or ""
    cached_src = entry.get("save_path_source", "cache") or "cache"

    if cached and cached_src != "userdata":
                                                                            
                                                                            
        if _is_steam_userdata_path(cached, steam_path):
            ud = _steam_userdata_path(steam_path, appid)
            if ud:
                return ud, "userdata"
        return _expand_path(cached), cached_src

                                                                   
    pcgw_path, pcgw_tmpl = _pcgw_lookup_save_path_and_template(appid, steam_path)
    if pcgw_path:
        if pcgw_tmpl and _is_portable_template(pcgw_tmpl):
            update_game(appid, save_path_template=pcgw_tmpl)
        return pcgw_path, "pcgw"

                                                                             
                                                                           
    ud_path = _steam_userdata_path(steam_path, appid)
    if ud_path:
        return ud_path, "userdata"

                                                                           
                                                             
    if cached:
        return _expand_path(cached), cached_src

    return "", "unresolved"


def set_manual_path(appid: int, path: str, steam_path: str = "") -> dict:
                                                                            
    tmpl = _abs_to_template(path, steam_path)
    return update_game(
        appid,
        save_path=path,
        save_path_source="manual",
        save_path_template=tmpl if _is_portable_template(tmpl) else "",
    )