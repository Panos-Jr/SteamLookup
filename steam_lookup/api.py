import json
import re
import urllib.request
import urllib.parse
import threading
import time

from . import lazy
from .config import (
    BROWSER_HEADERS, PCGW, DRM_META, THIRD_PARTY_KW,
)


                                                                                
def http_get_json(url, params=None, timeout=12):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def safe_get_json(url, params=None, timeout=12):
    try:
        return http_get_json(url, params, timeout)
    except Exception:
        return None


                                                                                
def search_steam(query: str):
                                                                                  
    enc  = urllib.parse.quote(query)
    url  = f"https://store.steampowered.com/api/storesearch/?term={enc}&l=english&cc=us"
    data = http_get_json(url, timeout=12)
    items = data.get("items", [])
    total = data.get("total", len(items))
    games = [{"appid": it["id"], "name": it["name"]}
             for it in items if it.get("id") and it.get("name")]
    return games, total


def steam_appdetails(appid: int):
                                                       
    d = safe_get_json("https://store.steampowered.com/api/appdetails",
                      {"appids": appid, "cc": "us", "l": "en"})
    if not d:
        return None
    return d.get(str(appid), {}).get("data")


                                                                                
def _classify_raw(raw: str):
    low = raw.lower().strip()
    if "denuvo" in low:
        return "denuvo", raw
    if "always online" in low or "always-online" in low:
        return "always_online", raw
    for kw, label in THIRD_PARTY_KW:
        if kw in low:
            return "thirdparty", label
    if "drm-free" in low or "drm free" in low or low in ("none", "no drm"):
        return "none", "DRM-Free"
    if "steam" in low or "steamworks" in low or "valve anti-cheat" in low or "vac" in low:
        return "steamworks", raw
    return "thirdparty", raw


def _make_desc(drm_type: str, label: str, extras: list) -> str:
    base = {
        "denuvo":        f"{label} — kernel/user-mode anti-tamper on top of Steam.",
        "always_online": f"{label} — requires a persistent internet connection.",
        "thirdparty":    f"{label} — requires an external launcher or account.",
        "steamworks":    f"{label} — standard Steam integration. Requires Steam client.",
        "none":          "No DRM. Runs without Steam active.",
        "unknown":       "No DRM data found.",
    }.get(drm_type, label)
    if extras:
        base += "  Also: " + ", ".join(extras) + "."
    return base


def get_drm(appid: int) -> dict:
                                             
    if appid in (1314140, 1736400):
        color, icon, _ = DRM_META["denuvo"]
        return {"type": "aderow", "label": "Aderow Anti-Tamper",
                "color": color, "icon": icon, "desc": "", "extras": [],
                "always_online": False, "anticheat": None}

                            
    page_name = None
    for where_clause in (
        f'Infobox_game."Steam AppID" HOLDS \'{appid}\'',
        f'Infobox_game."Steam AppID" = \'{appid}\'',
    ):
        data = safe_get_json(PCGW, {
            "action": "cargoquery", "format": "json",
            "tables": "Infobox_game", "fields": "_pageName=page",
            "where": where_clause, "limit": "5",
        })
        if data:
            rows = data.get("cargoquery", [])
            if rows:
                page_name = rows[0].get("title", {}).get("page", "").strip()
                if page_name:
                    break

    always_online = False
    anticheat     = None

    if page_name:
        safe_page = page_name.replace("'", "''")
        drm_data  = safe_get_json(PCGW, {
            "action": "cargoquery", "format": "json",
            "tables": "DRM", "fields": "DRM,Notes",
            "where": f"DRM._pageName = '{safe_page}'", "limit": "20",
        })
        classified = []
        if drm_data:
            for item in drm_data.get("cargoquery", []):
                raw = (item.get("title", {}).get("DRM") or "").strip()
                if raw:
                    typ, lbl = _classify_raw(raw)
                    classified.append((typ, lbl))
                    if typ == "always_online":
                        always_online = True

        ac_data = safe_get_json(PCGW, {
            "action": "cargoquery", "format": "json",
            "tables": "AntiCheat", "fields": "Name,Notes",
            "where": f"AntiCheat._pageName = '{safe_page}'", "limit": "5",
        })
        if ac_data:
            names = [ac["title"]["Name"].strip()
                     for ac in ac_data.get("cargoquery", [])
                     if ac.get("title", {}).get("Name")]
            if names:
                anticheat = ", ".join(names)

        if classified:
            prio = {k: v[2] for k, v in DRM_META.items()}
            classified.sort(key=lambda x: prio.get(x[0], 9))
            primary_type, primary_label = classified[0]
            extras = [lbl for _, lbl in classified[1:]]
            color, icon, _ = DRM_META[primary_type]
            return {"type": primary_type, "label": primary_label,
                    "color": color, "icon": icon,
                    "desc": _make_desc(primary_type, primary_label, extras),
                    "extras": extras, "always_online": always_online,
                    "anticheat": anticheat}

        color, icon, _ = DRM_META["none"]
        return {"type": "none", "label": "DRM-Free", "color": color, "icon": icon,
                "desc": "PCGamingWiki lists no DRM for this title.", "extras": [],
                "always_online": always_online, "anticheat": anticheat}

                             
    app_info = steam_appdetails(appid)
    if app_info:
        drm_notice  = app_info.get("drm_notice", "") or ""
        ext_account = app_info.get("ext_user_account_notice", "") or ""
        notice_text = re.sub(r"<[^>]+>", "", drm_notice).strip()
        ext_text    = re.sub(r"<[^>]+>", "", ext_account).strip()
        if "denuvo" in drm_notice.lower():
            color, icon, _ = DRM_META["denuvo"]
            return {"type": "denuvo", "label": "Denuvo Anti-Tamper",
                    "color": color, "icon": icon,
                    "desc": "Denuvo kernel-level protection detected via Steam store.",
                    "extras": [], "always_online": always_online, "anticheat": anticheat}
        if notice_text or ext_text:
            color, icon, _ = DRM_META["thirdparty"]
            return {"type": "thirdparty", "label": notice_text or ext_text,
                    "color": color, "icon": icon,
                    "desc": "Third-party DRM or external account requirement detected via Steam.",
                    "extras": [], "always_online": always_online, "anticheat": anticheat}
        if not app_info.get("is_free", False):
            color, icon, _ = DRM_META["steamworks"]
            return {"type": "steamworks", "label": "Steamworks",
                    "color": color, "icon": icon,
                    "desc": "No additional DRM found. Standard Steamworks integration.",
                    "extras": [], "always_online": always_online, "anticheat": anticheat}

    color, icon, _ = DRM_META["unknown"]
    return {"type": "unknown", "label": "Unknown", "color": color, "icon": icon,
            "desc": "No DRM information found on PCGamingWiki or Steam.", "extras": [],
            "always_online": always_online, "anticheat": anticheat}


                                                                                
def get_hubcap_stats(api_key: str):
                                                                        
    if not api_key:
        return "API key not set."
    requests = lazy.get_requests()
    url = "https://hubcapmanifest.com/api/v1/user/stats"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return f"Request failed: {e}"


                                                                                
def download_image_bytes(url: str, timeout: int = 10) -> bytes:
    requests = lazy.get_requests()
    return requests.get(url, timeout=timeout).content