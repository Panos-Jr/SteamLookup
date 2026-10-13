import re
from pathlib import Path
from typing import Optional

try:
    from .manifest import get_active_steamid3
except ImportError:
    get_active_steamid3 = None                


_TOKEN_RE = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')


def _parse_vdf(text: str) -> dict:
    text = re.sub(r'^\s*//.*$', '', text, flags=re.MULTILINE)

    tokens = []
    for m in _TOKEN_RE.finditer(text):
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
            existing = stack[-1].get(val)
                                                                            
            child = existing if isinstance(existing, dict) else {}
            stack[-1][val] = child
            stack.append(child)
            i += 2
        elif nxt and nxt[0] == "s":
            stack[-1][val] = nxt[1]
            i += 2
        else:
            i += 1
    return root


def _ci_children(d, key: str):
                                                                       
    if not isinstance(d, dict):
        return
    for k, v in d.items():
        if k.lower() == key.lower() and isinstance(v, dict):
            yield v


def _ci_value(d, key: str):
                                                                       
    if not isinstance(d, dict):
        return None
    for k, v in d.items():
        if k.lower() == key.lower() and not isinstance(v, dict):
            return v
    return None


def _walk(nodes, path):
                                                                        
    for key in path:
        nxt = []
        for n in nodes:
            nxt.extend(_ci_children(n, key))
        nodes = nxt
        if not nodes:
            return []
    return nodes


def _to_int(raw) -> Optional[int]:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _candidate_configs(steam_path: str):
                                                                             
    userdata = Path(steam_path) / "userdata"

    if get_active_steamid3 is not None:
        try:
            steamid3 = get_active_steamid3(steam_path)
        except Exception:
            steamid3 = None
        if steamid3:
            p = userdata / str(steamid3) / "config" / "localconfig.vdf"
            if p.is_file():
                yield p
                return

    if userdata.is_dir():
        found = [p for p in userdata.glob("*/config/localconfig.vdf") if p.is_file()]
        found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        yield from found


def _playtime_from_file(vdf_path: Path, appid: int) -> Optional[int]:
    try:
        text = vdf_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    root = _parse_vdf(text)

    tops = list(_ci_children(root, "UserLocalConfigStore")) or [root]

    entries = _walk(tops, ["Software", "Valve", "Steam", "Apps", str(appid)])
    for entry in entries:
        for key in ("Playtime", "playtime_forever", "PlayTime"):
            minutes = _to_int(_ci_value(entry, key))
            if minutes is not None:
                return minutes
    return None


def get_local_playtime(appid: int, steam_path: str) -> Optional[int]:
    if not steam_path:
        return None

    for vdf_path in _candidate_configs(steam_path):
        minutes = _playtime_from_file(vdf_path, appid)
        if minutes is not None:
            return minutes
    return None


def get_local_hours(appid: int, steam_path: str) -> Optional[float]:
    minutes = get_local_playtime(appid, steam_path)
    return None if minutes is None else round(minutes / 60, 1)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("usage: python steam_local.py <appid> <steam_path>")
        raise SystemExit(1)
    app, path = int(sys.argv[1]), sys.argv[2]
    mins = get_local_playtime(app, path)
    if mins is None:
        print("No local playtime found.")
    else:
        print(f"{mins} minutes ({mins / 60:.1f} hours)")