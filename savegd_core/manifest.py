import glob
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .config import BROWSER_HEADERS, PCGW_API, PCGW_APPID, PCGW_HEADERS
from .paths import manifest_file


STEAMID64_BASE = 76561197960265728

_LOCK = threading.RLock()


def load_manifest() -> dict:
    mf = manifest_file()
    try:
        with open(mf, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("bad shape")
            data.setdefault("version", 2)
            data.setdefault("drive_root", "SteamLookup_Saves")
            data.setdefault("games", {})
            return data
    except Exception:
        return {"version": 2, "drive_root": "SteamLookup_Saves", "games": {}}


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
    if not template:
        return ""
    if not _TEMPLATE_PATTERN.search(template):
        return _expand_path(template)

    ph = _build_placeholders(appid, steam_path or "")
    expanded = _expand_placeholders(template, ph)
    return expanded[0] if expanded else ""


def _is_portable_template(s: str) -> bool:
    return bool(s and _TEMPLATE_PATTERN.search(s))


def _save_paths_from_save_path(save_path: str,
                               save_path_template: str = "") -> list:
    if not save_path and not save_path_template:
        return []
    kind = "file"
    if save_path and os.path.isdir(save_path):
        kind = "dir"
    return [{
        "kind":     kind,
        "template": save_path_template or "",
        "path":     save_path or "",
    }]


def _expand_save_paths(entry: dict, steam_path: str) -> list:
    paths = entry.get("save_paths") or []
    if not paths:
        return _save_paths_from_save_path(
            entry.get("save_path") or "",
            entry.get("save_path_template") or "",
        )

    try:
        appid = int(entry.get("appid") or 0)
    except (TypeError, ValueError):
        appid = 0

    out = []
    for sp in paths:
        if not isinstance(sp, dict):
            continue
        tmpl = sp.get("template") or ""
        local = sp.get("path") or ""
        if tmpl and _is_portable_template(tmpl):
            expanded = _template_to_abs(tmpl, appid, steam_path)
            if expanded:
                local = expanded
        kind = sp.get("kind") or ("file" if (local and os.path.isfile(local))
                                  else "dir")
        out.append({"kind": kind, "template": tmpl, "path": local})
    return out


def _save_paths_to_template_list(save_paths: list, steam_path: str) -> list:
    out = []
    for sp in save_paths or []:
        path = (sp.get("path") or "").strip()
        if not path:
            continue
        kind = sp.get("kind")
        if not kind:
            kind = "file" if os.path.isfile(path) else "dir"
        tmpl = sp.get("template") or ""
        if not tmpl:
            maybe = _abs_to_template(path, steam_path)
            if _is_portable_template(maybe):
                tmpl = maybe
        out.append({"kind": kind, "template": tmpl, "path": path})
    return out


def get_game(appid: int):
    return load_manifest()["games"].get(str(appid))


def is_enrolled(appid: int) -> bool:
    return str(appid) in load_manifest()["games"]


def enroll_and_resolve(appid: int, name: str, steam_path: str) -> dict:
    enroll_game(appid, name, steam_path=steam_path)
    paths, src = resolve_save_paths(appid, steam_path)
    if paths:
        templated = _save_paths_to_template_list(paths, steam_path)
        first = templated[0]
        return update_game(
            appid,
            save_paths=templated,
            save_path=first["path"],
            save_path_template=first["template"],
            save_path_source=src,
        )
    return get_game(appid)


def enroll_game(appid: int, name: str, steam_path: str = "",
                save_path: str = "", save_path_source: str = "",
                save_path_template: str = "",
                save_paths: list = None) -> dict:
    with _LOCK:
        data = load_manifest()
        key  = str(appid)
        existing = data["games"].get(key, {})

        new_paths = save_paths
        if new_paths is None:
            new_paths = existing.get("save_paths") or []
        if not new_paths and (save_path or save_path_template):
            new_paths = _save_paths_from_save_path(save_path, save_path_template)

        entry = {
            "appid":              appid,
            "name":               name,
            "save_paths":         new_paths,
            "save_path":          save_path or existing.get("save_path", ""),
            "save_path_template": (save_path_template
                                   or existing.get("save_path_template", "")),
            "save_path_source":   save_path_source or existing.get("save_path_source", ""),
            "save_path_extras":   existing.get("save_path_extras", []),
            "auto_download":      existing.get("auto_download", False),
            "last_sync":          existing.get("last_sync"),
            "last_upload":        existing.get("last_upload"),
            "last_download":      existing.get("last_download"),
            "enrolled_at":        existing.get("enrolled_at", time.time()),
            "deployed_dirs":      existing.get("deployed_dirs", []),
            "proxy_dirs":         existing.get("proxy_dirs", []),
        }

        if entry["save_paths"]:
            first = entry["save_paths"][0]
            entry["save_path"] = first.get("path") or entry["save_path"]
            if not entry["save_path_template"] and first.get("template"):
                entry["save_path_template"] = first["template"]

        data["games"][key] = entry
        save_manifest(data)
        return entry


def unenroll_game(appid: int):
    with _LOCK:
        data = load_manifest()
        data["games"].pop(str(appid), None)
        save_manifest(data)


def update_game(appid: int, **fields):
    with _LOCK:
        data = load_manifest()
        key  = str(appid)
        if key not in data["games"]:
            return None
        data["games"][key].update(fields)
        if "save_paths" in fields and fields["save_paths"]:
            first = fields["save_paths"][0]
            if first.get("path"):
                data["games"][key]["save_path"] = first["path"]
            if first.get("template"):
                data["games"][key]["save_path_template"] = first["template"]
        save_manifest(data)
        return data["games"][key]


def all_games() -> list:
    data = load_manifest()
    return sorted(data["games"].values(), key=lambda g: g.get("name", "").lower())


def migrate_entries_to_save_paths(steam_path: str) -> int:
    with _LOCK:
        data = load_manifest()
        games = data.get("games") or {}
        changed = 0

        for key, entry in games.items():
            if not isinstance(entry, dict):
                continue
            if entry.get("save_paths"):
                continue
            sp = entry.get("save_path") or ""
            tmpl = entry.get("save_path_template") or ""
            if not sp and not tmpl:
                entry["save_paths"] = []
                changed += 1
                continue
            entry["save_paths"] = _save_paths_from_save_path(sp, tmpl)
            changed += 1

        if changed:
            data["version"] = max(int(data.get("version", 1)), 2)
            save_manifest(data)
        return changed


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
    params = {"action": "parse", "page": title,
              "prop": "wikitext", "format": "json"}
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


def _expand_path(p: str) -> str:
    if not p:
        return ""
    p = p.strip().strip('"').strip("'")
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


def _pcgw_resolve_paths(appid: int, steam_path: str) -> list:
    templates = _pcgw_save_templates(appid)
    if not templates:
        return []

    raw_paths = _rank_save_sections(templates)
    if not raw_paths:
        return []

    placeholders = _build_placeholders(appid, steam_path or "")

    results = []
    seen_paths = set()

    for raw in raw_paths:
        expanded_list = _expand_placeholders(raw, placeholders)
        if not expanded_list:
            continue

        for expanded in expanded_list:
            norm = os.path.normpath(expanded).lower()
            if norm in seen_paths:
                continue
            seen_paths.add(norm)

            kind = "file" if os.path.isfile(expanded) else "dir"
            if not os.path.exists(expanded):
                base = os.path.basename(expanded)
                kind = "file" if "." in base else "dir"

            results.append({
                "kind":     kind,
                "template": raw,
                "path":     expanded,
            })

    return results


def _pcgw_lookup_save_path(appid: int, steam_path: str = "") -> str:
    results = _pcgw_resolve_paths(appid, steam_path)
    if not results:
        return ""
    for r in results:
        if os.path.exists(r["path"]):
            return r["path"]
    return results[0]["path"]


def _pcgw_lookup_template(appid: int, steam_path: str = "") -> str:
    results = _pcgw_resolve_paths(appid, steam_path)
    if not results:
        return ""
    for r in results:
        if os.path.exists(r["path"]):
            return r["template"]
    return results[0]["template"]


def _pcgw_lookup_save_paths(appid: int, steam_path: str) -> list:
    return _pcgw_resolve_paths(appid, steam_path)


def resolve_save_paths(appid: int, steam_path: str) -> tuple:
    entry = get_game(appid) or {}

    existing = _expand_save_paths(entry, steam_path)
    if existing:
        if any(sp.get("template") for sp in existing):
            return existing, "template"
        src = entry.get("save_path_source") or "cache"
        if src == "userdata":
            pass
        else:
            return existing, src

    legacy_path = entry.get("save_path") or ""
    legacy_tmpl = entry.get("save_path_template") or ""
    legacy_src  = entry.get("save_path_source") or "cache"

    if (legacy_path or legacy_tmpl) and legacy_src != "userdata":
        if not existing:
            synth = _save_paths_from_save_path(legacy_path, legacy_tmpl)
            if synth:
                return synth, legacy_src

    pcgw_paths = _pcgw_lookup_save_paths(appid, steam_path)
    if pcgw_paths:
        updates = {"save_paths": pcgw_paths}
        if len(pcgw_paths) > 1:
            updates["save_path_source"] = "pcgw-multi"
        else:
            updates["save_path_source"] = "pcgw"
        try:
            update_game(appid, **updates)
        except Exception:
            pass
        return pcgw_paths, updates["save_path_source"]

    ud_path = _steam_userdata_path(steam_path, appid)
    if ud_path:
        synth = [{"kind": "dir", "template": "", "path": ud_path}]
        return synth, "userdata"

    if legacy_path:
        synth = _save_paths_from_save_path(legacy_path, legacy_tmpl)
        return synth, legacy_src

    return [], "unresolved"


def resolve_save_path(appid: int, steam_path: str) -> tuple:
    paths, src = resolve_save_paths(appid, steam_path)
    if not paths:
        return "", src
    return paths[0]["path"], src


def set_manual_path(appid: int, path: str, steam_path: str = "") -> dict:
    kind = "file" if os.path.isfile(path) else "dir"
    tmpl = _abs_to_template(path, steam_path)
    sp = [{
        "kind":     kind,
        "template": tmpl if _is_portable_template(tmpl) else "",
        "path":     path,
    }]
    return update_game(
        appid,
        save_paths=sp,
        save_path=path,
        save_path_source="manual",
        save_path_template=sp[0]["template"],
    )


def refresh_weak_paths(steam_path: str) -> list:
    changed = []

    with _LOCK:
        data = load_manifest()
        games = data.get("games") or {}

        for key, entry in list(games.items()):
            if not isinstance(entry, dict):
                continue

            source = entry.get("save_path_source") or ""
            if source == "manual":
                continue

            needs_refresh = False
            if source in ("userdata", ""):
                needs_refresh = True
            elif not (entry.get("save_paths") or entry.get("save_path")):
                needs_refresh = True

            if not needs_refresh:
                continue

            try:
                appid = int(entry.get("appid") or key)
            except (TypeError, ValueError):
                continue

            try:
                new_paths, new_src = resolve_save_paths(appid, steam_path)
            except Exception:
                continue

            if not new_paths:
                continue

            if new_src == "userdata" and source == "userdata":
                continue

            old_first = ""
            if entry.get("save_paths"):
                old_first = (entry["save_paths"][0].get("path") or "")
            elif entry.get("save_path"):
                old_first = entry["save_path"]

            new_first = new_paths[0].get("path") or ""

            if new_first == old_first and new_src == source:
                continue

            entry["save_paths"] = new_paths
            entry["save_path"] = new_first
            entry["save_path_template"] = new_paths[0].get("template") or ""
            entry["save_path_source"] = new_src

            changed.append((entry.get("name", f"AppID {appid}"),
                            old_first, new_first))

        if changed:
            save_manifest(data)

    return changed