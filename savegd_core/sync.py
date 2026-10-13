"""
sync.py — Google Drive sync for save_gd.

Handles zipping, hashing, uploading, downloading, history archiving,
and the games.json manifest replication.

How "which side is newer" is decided
------------------------------------
Neither timestamps nor playtime are trustworthy on their own (clocks differ,
extracting a zip resets file times, playtime is per-PC). Instead each PC
remembers the state of the last sync, per game:

    base.local   hash of this PC's save files when we last synced
    base.remote  hash of the Google Drive copy when we last synced

Hashes are of file *contents* (not of the zip, whose bytes change whenever a
file's timestamp changes). Then, comparing with now:

    local == remote                       -> in sync
    only the Drive copy changed           -> cloud_newer  (safe to download)
    only this PC changed                  -> local_newer  (safe to upload)
    both changed                          -> conflict     (never auto-overwritten)

The very first time a PC sees a game (no base yet) there is nothing to compare
against, so playtime (when both sides have it) and then timestamps are used as
a tiebreaker.

Save targets
------------
A save target is either a folder (most games) or a single file (some games,
e.g. Sleeping Dogs). Everything in this module dispatches on the type via
`_resolve_target`, which returns ("file", path) | ("dir", path) | ("missing",
path). Zipping a single file produces a one-entry zip; unzipping into a file
path extracts the single entry back to disk. Hashing is consistent between
both shapes.

Lazy-imports the Google libraries so this module has no hard dependency
on google-auth / google-api-python-client at import time.
"""

import hashlib
import io
import json
import os
import time
import zipfile
from pathlib import Path

from .config import GOOGLE_SCOPES, DRIVE_ROOT_FOLDER


# First-contact tiebreak: playtimes closer than this (minutes) count as equal.
FIRST_CONTACT_PLAYTIME_GAP_MIN = 5

# Single source of truth for the "we're zipping a single file" sentinel name
# inside the zip. Using a fixed name means content_hash_zip is stable across
# uploads regardless of the source filename.
_SINGLE_FILE_ARCNAME = "__save_file__"


# ── Lazy google libs ──────────────────────────────────────────────────────────

_google_creds = None
_google_drive = None
_google_http  = None


def _load_google_libs():
    global _google_creds, _google_drive, _google_http
    if _google_creds is not None:
        return

    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

    _google_creds = Credentials
    _google_drive = (build, MediaFileUpload, MediaIoBaseDownload)
    _google_http  = Request


# ── Target resolution ─────────────────────────────────────────────────────────

def _resolve_target(path: str):
    """
    Return (kind, resolved_path) where kind is "file", "dir", or "missing".
    """
    if not path:
        return "missing", Path(path) if path else None
    p = Path(path)
    if p.is_file():
        return "file", p
    if p.is_dir():
        return "dir", p
    return "missing", p


# ── Zip / hash helpers ────────────────────────────────────────────────────────

def _sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _combine(entries) -> str:
    """entries: iterable of (relative_posix_path, file_sha256_hex), any order."""
    h = hashlib.sha256()
    for rel, file_hash in sorted(entries, key=lambda e: e[0]):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(file_hash.encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def _content_hash_dir(folder: Path) -> str:
    entries = []
    for root, _dirs, files in os.walk(folder):
        for fname in files:
            full = Path(root) / fname
            try:
                rel = full.relative_to(folder).as_posix()
                entries.append((rel, _file_sha256(full)))
            except Exception:
                pass
    return _combine(entries)


def _content_hash_file(path: Path) -> str:
    try:
        return _combine([(_SINGLE_FILE_ARCNAME, _file_sha256(path))])
    except Exception:
        return _combine([])


def content_hash_folder(folder: str) -> str:
    """
    Hash of the save files' relative paths + contents. Accepts either a folder
    or a single file; for a file, the hash is of the file content under a
    fixed arcname so it's stable across uploads.
    """
    kind, target = _resolve_target(folder)
    if kind == "dir":
        return _content_hash_dir(target)
    if kind == "file":
        return _content_hash_file(target)
    return _combine([])


def content_hash_zip(blob: bytes) -> str:
    """Same hash as content_hash_folder, computed from a save.zip's bytes."""
    entries = []
    try:
        with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                rel = info.filename.replace("\\", "/")
                entries.append((rel, _sha256(zf.read(info))))
    except Exception:
        return _combine([])
    return _combine(entries)


# ZIP_STORED vs ZIP_DEFLATED: saves are usually binary and mostly incompressible,
# so deflate burns CPU for ~1-3% size reduction. Stored is much faster to build
# and to extract, which is what actually bottlenecks the sync round-trip.
_ZIP_MODE = zipfile.ZIP_STORED


def zip_folder(folder: str) -> bytes:
    kind, target = _resolve_target(folder)
    if kind == "missing":
        return b""

    buf = io.BytesIO()

    if kind == "file":
        try:
            with zipfile.ZipFile(buf, "w", _ZIP_MODE) as zf:
                zf.write(target, _SINGLE_FILE_ARCNAME)
        except Exception:
            return b""
        return buf.getvalue()

    # Directory
    has_files = False
    try:
        with zipfile.ZipFile(buf, "w", _ZIP_MODE) as zf:
            for root, _dirs, files in os.walk(target):
                for fname in files:
                    full = Path(root) / fname
                    rel  = full.relative_to(target)
                    try:
                        zf.write(full, str(rel))
                        has_files = True
                    except Exception:
                        pass
    except Exception:
        return b""
    return buf.getvalue() if has_files else b""


def unzip_into(blob: bytes, target_path: str):
    """
    Extract save.zip's contents into either a folder or a file.

    - If target_path currently resolves to a directory (or doesn't exist and
      has no extension suggesting a file), extract as a folder tree.
    - If target_path resolves to a file, extract the single entry back to it.
      If the zip has multiple entries we extract the first one and warn by
      returning its name; the caller's UI can surface that.
    """
    kind, target = _resolve_target(target_path)

    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        members = [i for i in zf.infolist() if not i.is_dir()]

        if kind == "file" or (
            kind == "missing" and target and target.suffix
            and len(members) == 1
        ):
            # Single-file restore. If the zip has more than one entry we still
            # write the first one, because the destination is a file path and
            # we can't do anything else sensible.
            if not members:
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(members[0], "r") as src:
                data = src.read()
            target.write_bytes(data)
            return

        # Folder restore
        target.mkdir(parents=True, exist_ok=True)
        zf.extractall(target)


def newest_mtime(target_path: str) -> float:
    kind, target = _resolve_target(target_path)
    if kind == "file":
        try:
            return os.path.getmtime(target)
        except Exception:
            return 0.0
    if kind != "dir":
        return 0.0

    newest = 0.0
    for root, _dirs, files in os.walk(target):
        for fname in files:
            try:
                t = os.path.getmtime(os.path.join(root, fname))
                if t > newest:
                    newest = t
            except Exception:
                pass
    return newest


# ── Per-PC sync state (what we last synced) ───────────────────────────────────

def _state_file() -> Path:
    from . import paths
    return paths.runtime_dir() / "save_gd_sync_state.json"


def _load_state() -> dict:
    try:
        with open(_state_file(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_base(appid):
    entry = _load_state().get(str(appid))
    if isinstance(entry, dict) and entry.get("local") and entry.get("remote"):
        return entry
    return None


def _record_base(appid, local_hash: str, remote_hash: str):
    base = _load_base(appid)
    if base and base["local"] == local_hash and base["remote"] == remote_hash:
        return
    state = _load_state()
    state[str(appid)] = {
        "local":  local_hash,
        "remote": remote_hash,
        "at":     time.time(),
    }
    try:
        path = _state_file()
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        pass


# ── Drive client ──────────────────────────────────────────────────────────────

class DriveClient:
    def __init__(self, token_path: str):
        _load_google_libs()
        self.token_path = token_path
        self.creds = None
        self.service = None

    def authenticate(self) -> bool:
        Credentials = _google_creds
        Request     = _google_http
        build, _, _ = _google_drive

        if os.path.exists(self.token_path):
            try:
                self.creds = Credentials.from_authorized_user_file(
                    self.token_path, scopes=GOOGLE_SCOPES,
                )
            except Exception:
                self.creds = None

        if self.creds and self.creds.expired and self.creds.refresh_token:
            try:
                self.creds.refresh(Request())
                self._save_token()
            except Exception:
                self.creds = None

        if not self.creds or not self.creds.valid:
            return False

        self.service = build("drive", "v3", credentials=self.creds)
        return True

    def _save_token(self):
        try:
            with open(self.token_path, "w", encoding="utf-8") as f:
                f.write(self.creds.to_json())
        except Exception:
            pass

    # ── Folder / file ops ────────────────────────────────────────────────

    def ensure_folder(self, name: str, parent: str = None) -> str:
        q = (f"mimeType='application/vnd.google-apps.folder' "
             f"and name='{name}' and trashed=false")
        if parent:
            q += f" and '{parent}' in parents"
        else:
            q += " and 'root' in parents"
        res = self.service.files().list(
            q=q, fields="files(id,name)", pageSize=1,
        ).execute()
        files = res.get("files", [])
        if files:
            return files[0]["id"]
        meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent:
            meta["parents"] = [parent]
        created = self.service.files().create(body=meta, fields="id").execute()
        return created["id"]

    def find_file(self, name: str, parent: str):
        q = f"name='{name}' and '{parent}' in parents and trashed=false"
        res = self.service.files().list(
            q=q,
            fields="files(id,name,modifiedTime,size,md5Checksum)",
            pageSize=1,
        ).execute()
        files = res.get("files", [])
        return files[0] if files else None

    def list_files(self, parent: str, page_size: int = 100):
        q = f"'{parent}' in parents and trashed=false"
        res = self.service.files().list(
            q=q, fields="files(id,name,modifiedTime,size)",
            pageSize=page_size,
        ).execute()
        return res.get("files", [])

    def upload_bytes(self, name: str, parent: str, blob: bytes,
                     mime: str = "application/zip") -> str:
        _, MediaFileUpload, _ = _google_drive
        tmp = Path(os.environ.get("TEMP", ".")) / f"_sd_up_{os.getpid()}_{name}"
        tmp.write_bytes(blob)
        existing = self.find_file(name, parent)
        # chunksize=-1 → single-shot upload. MediaFileUpload defaults to a
        # resumable 100MB-chunk upload which is slower for our small payloads.
        media = MediaFileUpload(str(tmp), mimetype=mime, resumable=False)
        try:
            if existing:
                self.service.files().update(
                    fileId=existing["id"], media_body=media,
                ).execute()
                return existing["id"]
            meta = {"name": name, "parents": [parent]}
            created = self.service.files().create(
                body=meta, media_body=media, fields="id",
            ).execute()
            return created["id"]
        finally:
            try:
                tmp.unlink()
            except Exception:
                pass

    def download_bytes(self, file_id: str) -> bytes:
        _, _, MediaIoBaseDownload = _google_drive
        buf = io.BytesIO()
        request = self.service.files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue()

    def delete_file(self, file_id: str):
        try:
            self.service.files().delete(fileId=file_id).execute()
        except Exception:
            pass


# ── High-level helpers ────────────────────────────────────────────────────────

def _drive_root(client: DriveClient) -> str:
    return client.ensure_folder(DRIVE_ROOT_FOLDER)


def _drive_game_folder(client: DriveClient, appid: int) -> str:
    root_id = _drive_root(client)
    return client.ensure_folder(str(appid), parent=root_id)


def _drive_history_folder(client: DriveClient, game_id: str) -> str:
    return client.ensure_folder("history", parent=game_id)


def _drive_meta(client: DriveClient, game_id: str) -> dict:
    f = client.find_file("meta.json", game_id)
    if not f:
        return {}
    try:
        blob = client.download_bytes(f["id"])
        return json.loads(blob.decode("utf-8", errors="replace"))
    except Exception:
        return {}


def _write_meta(client: DriveClient, game_id: str, meta: dict):
    client.upload_bytes(
        "meta.json", game_id,
        json.dumps(meta, indent=2).encode("utf-8"),
        mime="application/json",
    )


def _remote_content_hash(client: DriveClient, game_id: str, meta: dict):
    existing = meta.get("content_hash")
    if existing:
        return existing
    if not meta.get("hash"):
        return None

    f = client.find_file("save.zip", game_id)
    if not f:
        return None
    try:
        blob = client.download_bytes(f["id"])
        value = content_hash_zip(blob)
    except Exception:
        return None

    meta["content_hash"] = value
    try:
        _write_meta(client, game_id, meta)
    except Exception:
        pass
    return value


def _prune_history(client: DriveClient, history_id: str, keep: int = 20):
    try:
        files = client.list_files(history_id, page_size=100)
        if len(files) > keep:
            files.sort(key=lambda f: f["name"])
            for old in files[:-keep]:
                client.delete_file(old["id"])
    except Exception:
        pass


def _archive_blob(client: DriveClient, game_id: str, blob: bytes, tag: str = ""):
    history_id = _drive_history_folder(client, game_id)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    name = f"{stamp}_{tag}.zip" if tag else f"{stamp}.zip"
    client.upload_bytes(name, history_id, blob, mime="application/zip")
    _prune_history(client, history_id)


def _archive_current(client: DriveClient, game_id: str):
    current = client.find_file("save.zip", game_id)
    if not current:
        return
    try:
        blob = client.download_bytes(current["id"])
    except Exception:
        return
    _archive_blob(client, game_id, blob)


def _do_upload(client: DriveClient, game_id: str, appid: int,
               blob: bytes, hash_hex: str, steam_path: str = "",
               content_hash: str = ""):
    client.upload_bytes("save.zip", game_id, blob, mime="application/zip")

    playtime = _local_playtime(appid, steam_path)

    meta = {
        "appid":        appid,
        "hash":         hash_hex,
        "content_hash": content_hash or content_hash_zip(blob),
        "uploaded_at":  time.time(),
        "size":         len(blob),
    }
    if playtime is not None:
        meta["playtime_minutes"] = playtime
        meta["playtime_source"]  = "local_vdf"

    _write_meta(client, game_id, meta)


def _do_download(client: DriveClient, game_id: str, save_path: str):
    f = client.find_file("save.zip", game_id)
    if not f:
        raise RuntimeError("save.zip missing on Google Drive.")
    blob = client.download_bytes(f["id"])
    unzip_into(blob, save_path)


def _local_playtime(appid: int, steam_path: str):
    if not steam_path:
        return None
    try:
        from .steam_local import get_local_playtime
        return get_local_playtime(appid, steam_path)
    except Exception:
        return None


# ── Deciding what should happen ───────────────────────────────────────────────

def _decide(appid: int, save_path: str, local_hash: str, remote_hash,
            meta: dict, steam_path: str) -> str:
    if remote_hash is None:
        return "no_cloud"
    if local_hash == remote_hash:
        return "in_sync"

    base = _load_base(appid)
    if base is not None:
        remote_changed = remote_hash != base["remote"]
        local_changed  = local_hash  != base["local"]
        if remote_changed and local_changed:
            return "conflict"
        if remote_changed:
            return "cloud_newer"
        if local_changed:
            return "local_newer"
        return "in_sync"

    # First-contact tiebreak
    local_pt  = _local_playtime(appid, steam_path)
    remote_pt = meta.get("playtime_minutes")
    if (local_pt is not None and remote_pt is not None
            and abs(local_pt - remote_pt) > FIRST_CONTACT_PLAYTIME_GAP_MIN):
        return "cloud_newer" if remote_pt > local_pt else "local_newer"

    local_mtime = newest_mtime(save_path)
    remote_time = meta.get("uploaded_at", 0) or 0
    return "local_newer" if local_mtime >= remote_time else "cloud_newer"


def compare_game(appid: int, save_path: str, client: DriveClient,
                 steam_path: str = "") -> dict:
    info = {"state": "unknown", "remote_time": 0,
            "remote_playtime": None, "message": ""}

    kind, _target = _resolve_target(save_path)
    if kind == "missing":
        info["message"] = f"Save target not found: {save_path}"
        return info

    try:
        game_id = _drive_game_folder(client, appid)
        meta    = _drive_meta(client, game_id)
        remote_hash = _remote_content_hash(client, game_id, meta)
    except Exception as e:
        info["message"] = f"Google Drive access failed: {e}"
        return info

    info["remote_time"]     = meta.get("uploaded_at", 0) or 0
    info["remote_playtime"] = meta.get("playtime_minutes")

    local_hash = content_hash_folder(save_path)
    state = _decide(appid, save_path, local_hash, remote_hash, meta, steam_path)
    if state == "in_sync" and remote_hash is not None:
        _record_base(appid, local_hash, remote_hash)
    info["state"] = state
    return info


def sync_game(appid: int, save_path: str, client: DriveClient,
              auto_download: bool, steam_path: str = "",
              direction: str = "") -> dict:
    result = {
        "action":      "skipped",
        "message":     "",
        "state":       None,
        "conflict":    False,
        "local_hash":  None,
        "remote_hash": None,
        "archived":    False,
        "warning":     None,
    }

    kind, _target = _resolve_target(save_path)
    if kind == "missing":
        result.update(action="error",
                      message=f"Save target not found: {save_path}")
        return result

    local_blob = zip_folder(save_path)
    if not local_blob:
        result.update(action="error",
                      message="Save target is empty, nothing to sync.")
        return result

    local_hash = content_hash_folder(save_path)
    result["local_hash"] = local_hash

    try:
        game_id = _drive_game_folder(client, appid)
        meta    = _drive_meta(client, game_id)
        remote_hash = _remote_content_hash(client, game_id, meta)
    except Exception as e:
        result.update(action="error", message=f"Google Drive access failed: {e}")
        return result

    result["remote_hash"] = remote_hash

    state = _decide(appid, save_path, local_hash, remote_hash, meta, steam_path)
    result["state"] = state

    def do_upload(archive_remote: bool, message: str, warning: str = None):
        if archive_remote:
            _archive_current(client, game_id)
            result["archived"] = True
        _do_upload(client, game_id, appid, local_blob,
                   _sha256(local_blob), steam_path, content_hash=local_hash)
        _record_base(appid, local_hash, local_hash)
        result.update(action="uploaded", message=message, warning=warning)

    def do_download(message: str, warning: str):
        _archive_blob(client, game_id, local_blob, tag="local")
        result["archived"] = True
        _do_download(client, game_id, save_path)
        _record_base(appid, content_hash_folder(save_path), remote_hash)
        result.update(action="downloaded", message=message, warning=warning)

    if state == "no_cloud":
        if direction == "download":
            result.update(action="error",
                          message="There is nothing on Google Drive to download.")
            return result
        do_upload(False, "First upload to Google Drive.")
        return result

    if state == "in_sync":
        _record_base(appid, local_hash, remote_hash)
        result.update(action="skipped", message="Already in sync.")
        return result

    if direction == "upload":
        do_upload(
            True, "Uploaded to Google Drive.",
            "⚠ Uploaded. The previous Google Drive save was archived to "
            "history and replaced.",
        )
        return result

    if direction == "download":
        do_download(
            "Downloaded from Google Drive.",
            "⚠ Downloaded. Your previous local save was archived to "
            "Google Drive history and replaced.",
        )
        return result

    if state == "local_newer":
        do_upload(
            True, "Local newer — uploaded.",
            "⚠ Uploaded. The previous Google Drive save was archived to "
            "history and replaced.",
        )

    elif state == "cloud_newer":
        if auto_download:
            do_download(
                "Google Drive newer — downloaded.",
                "⚠ Downloaded. Your local save was archived to Google Drive "
                "history and replaced.",
            )
        else:
            result.update(
                action="skipped",
                message=("Google Drive is newer, but auto-download is off. "
                         "Use Download in Save Sync to pull it manually."),
            )

    else:  # conflict
        result.update(
            action="skipped",
            conflict=True,
            message=("Conflict: this PC and Google Drive both changed since the "
                     "last sync, so nothing was overwritten. Open Save Sync and "
                     "choose Upload or Download."),
        )

    return result


# ── games.json replication ────────────────────────────────────────────────────

def _manifest_for_push(manifest: dict) -> dict:
    """
    Strip PC-specific fields (absolute save_path, deployed/proxy dirs) before
    uploading. The portable save_path_template travels intact.
    """
    if not isinstance(manifest, dict):
        return manifest

    out = dict(manifest)
    games = {}
    for k, entry in (manifest.get("games") or {}).items():
        e = dict(entry)
        e.pop("save_path", None)
        e.pop("deployed_dirs", None)
        e.pop("proxy_dirs", None)
        games[k] = e
    out["games"] = games
    return out


def _manifest_after_pull(manifest: dict, steam_path: str) -> dict:
    """
    Re-expand save_path_template against this PC's environment. Entries
    without a template get a fresh resolve attempt so their local path is
    backfilled (and a template written for future cross-PC travel).
    """
    try:
        from . import manifest as sg_manifest
    except Exception:
        return manifest

    if not isinstance(manifest, dict):
        return manifest

    for key, entry in (manifest.get("games") or {}).items():
        if not isinstance(entry, dict):
            continue

        try:
            appid = int(entry.get("appid") or key)
        except (TypeError, ValueError):
            appid = 0

        tmpl = entry.get("save_path_template") or ""
        if tmpl:
            try:
                local = sg_manifest._template_to_abs(tmpl, appid, steam_path)
                if local:
                    entry["save_path"] = local
                    continue
            except Exception:
                pass

        # No template, or template didn't expand — try a full re-resolve.
        current = entry.get("save_path") or ""
        kind, _t = _resolve_target(current)
        if kind != "missing":
            continue

        try:
            resolved, source = sg_manifest.resolve_save_path(appid, steam_path)
        except Exception:
            resolved, source = "", ""

        if resolved:
            entry["save_path"] = resolved
            entry["save_path_source"] = source or entry.get("save_path_source", "")
            try:
                maybe_tmpl = sg_manifest._abs_to_template(resolved, steam_path)
                if sg_manifest._is_portable_template(maybe_tmpl):
                    entry["save_path_template"] = maybe_tmpl
            except Exception:
                pass
        else:
            entry["save_path"] = ""

    return manifest


def push_games_json(client: DriveClient, manifest_dict: dict) -> bool:
    try:
        root_id = _drive_root(client)
        portable = _manifest_for_push(manifest_dict)
        blob = json.dumps(portable, indent=2, ensure_ascii=False).encode("utf-8")
        client.upload_bytes("games.json", root_id, blob, mime="application/json")
        return True
    except Exception:
        return False


def pull_games_json(client: DriveClient) -> dict:
    try:
        root_id = _drive_root(client)
        f = client.find_file("games.json", root_id)
        if not f:
            return {}
        blob = client.download_bytes(f["id"])
        return json.loads(blob.decode("utf-8", errors="replace"))
    except Exception:
        return {}


def merge_games_json(local: dict, remote: dict, steam_path: str = "") -> dict:
    if not isinstance(local, dict):
        local = {}
    if not isinstance(remote, dict):
        remote = {}

    out = {
        "version":    remote.get("version", local.get("version", 1)),
        "drive_root": remote.get("drive_root",
                                 local.get("drive_root", "SteamLookup_Saves")),
        "games":      {},
    }

    for key, entry in (local.get("games") or {}).items():
        out["games"][key] = dict(entry)

    for key, entry in (remote.get("games") or {}).items():
        if key not in out["games"]:
            out["games"][key] = dict(entry)
            continue
        l_sync = out["games"][key].get("last_sync") or 0
        r_sync = entry.get("last_sync") or 0
        if r_sync >= l_sync:
            out["games"][key] = dict(entry)

    if steam_path:
        out = _manifest_after_pull(out, steam_path)

    return out