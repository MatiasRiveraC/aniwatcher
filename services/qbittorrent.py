"""
qBittorrent support, over its Web UI API (v2).

Torrents are added under one category (`qbit_category`) and saved to
`torrent_incoming`. qBittorrent has no "move when finished" that is safe to
rely on here, so `import_completed()` does the hand-off itself: when a torrent
in that category finishes, its files are put into `torrent_done`, where the
normal renamer takes over exactly as with Deluge. Two ways, by
`qbit_stop_seeding`:

- **Keep seeding** (default): the torrent stays in qBittorrent. Its files are
  hard-linked into `torrent_done` — a second name for the same data, so no
  extra space and nothing moves out from under qBittorrent — or copied where
  a hard link is impossible. The renamer copies them on into the library and
  only then strips titles, so the seeding files are never modified. The
  torrent is tagged `aniwatcher-imported` so it is handed over once.
- **Stop seeding**: the torrent is removed from qBittorrent, keeping the files,
  and they are moved into `torrent_done`. Removing it first matters:
  qBittorrent would otherwise go on seeding from a path that no longer exists
  and mark the torrent "missing files".

AniWatcher and qBittorrent must see the downloads at the same path (e.g. both
mount the host folder at /downloads), since qBittorrent reports its own paths.
"""

import os
import time
import shutil
import logging

import requests

log = logging.getLogger(__name__)

# States in which the files are complete and not being touched.
_BUSY_STATES = {
    "checkingUP", "checkingDL", "checkingResumeData", "moving",
    "metaDL", "allocating", "missingFiles", "error",
}

# Items left in the incoming folder with no torrent behind them (a move that
# failed after the torrent was removed) are moved on once they are this old.
_ORPHAN_AGE = 600

# Marks a torrent already handed to the renamer while it keeps seeding.
IMPORTED_TAG = "aniwatcher-imported"


def _s():
    from data import get_settings
    return get_settings()


class QbitError(RuntimeError):
    pass


class _Client:
    """A session that logs in when qBittorrent asks it to."""

    def __init__(self):
        self.session = requests.Session()
        self._login_for = None

    def _base(self, s) -> str:
        return s["qbit_url"].rstrip("/") + "/api/v2"

    def _login(self, s) -> None:
        r = self.session.post(self._base(s) + "/auth/login", timeout=10,
                              data={"username": s["qbit_user"], "password": s["qbit_pass"]})
        if r.status_code != 200 or r.text.strip() != "Ok.":
            raise QbitError(f"qBittorrent login failed ({r.status_code}: {r.text.strip()[:60]})")
        self._login_for = (s["qbit_url"], s["qbit_user"], s["qbit_pass"])

    def call(self, method: str, path: str, **kw) -> requests.Response:
        s = _s()
        # Settings changed in the UI: start a fresh session for the new server.
        if self._login_for and self._login_for != (s["qbit_url"], s["qbit_user"], s["qbit_pass"]):
            self.session = requests.Session()
            self._login_for = None
        url = self._base(s) + path
        r = self.session.request(method, url, timeout=15, **kw)
        if r.status_code == 403:  # not logged in, or the session expired
            self._login(s)
            r = self.session.request(method, url, timeout=15, **kw)
        if r.status_code >= 400:
            raise QbitError(f"{method} {path}: {r.status_code} {r.text.strip()[:80]}")
        return r


_client = _Client()


def _ensure_category(s) -> None:
    try:
        _client.call("POST", "/torrents/createCategory",
                     data={"category": s["qbit_category"], "savePath": s["torrent_incoming"]})
    except QbitError as e:
        if " 409 " not in str(e):  # 409: it already exists, which is fine
            raise


def add_torrent_to_qbittorrent(magnet_or_url: str) -> bool:
    s = _s()
    try:
        _ensure_category(s)
        r = _client.call("POST", "/torrents/add", data={
            "urls":     magnet_or_url,
            "category": s["qbit_category"],
            "savepath": s["torrent_incoming"],
            "autoTMM":  "false",
        })
        if r.text.strip() not in ("Ok.", ""):
            raise QbitError(f"add refused: {r.text.strip()[:80]}")
        log.info("Added torrent to qBittorrent")
        return True
    except (requests.RequestException, QbitError) as e:
        log.error(f"qBittorrent error: {e}")
        return False


def _torrents(s) -> list:
    return _client.call("GET", "/torrents/info", params={"category": s["qbit_category"]}).json()


def _unique(path: str) -> str:
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{stem} ({n}){ext}"):
        n += 1
    return f"{stem} ({n}){ext}"


def _move_into_done(src: str, done: str) -> str:
    dest = _unique(os.path.join(done, os.path.basename(src.rstrip("/"))))
    shutil.move(src, dest)  # a rename when both are on one filesystem
    return dest


def _link_or_copy(src: str, dest: str) -> None:
    try:
        os.link(src, dest)
    except OSError:  # another filesystem, or links not allowed: copy instead
        # Not shutil.copy2, which fails with EPERM on TrueNAS ACL datasets
        from services.renamer import copy_contents
        copy_contents(src, dest)


def _link_into_done(src: str, done: str) -> str:
    """Hard-link a torrent's file or folder into done, leaving the original seeding."""
    dest = _unique(os.path.join(done, os.path.basename(src.rstrip("/"))))
    try:
        if os.path.isdir(src):
            for root, _, files in os.walk(src):
                target = os.path.join(dest, os.path.relpath(root, src))
                os.makedirs(target, exist_ok=True)
                for f in files:
                    _link_or_copy(os.path.join(root, f), os.path.join(target, f))
        else:
            _link_or_copy(src, dest)
    except OSError:
        # Half a hand-off would be renamed as if whole; undo it and let the
        # next pass try again, since the torrent is not tagged yet.
        if os.path.isdir(dest):
            shutil.rmtree(dest, ignore_errors=True)
        elif os.path.exists(dest):
            os.remove(dest)
        raise
    return dest


def _tags(t: dict) -> set:
    return {x.strip() for x in (t.get("tags") or "").split(",") if x.strip()}


def import_completed() -> int:
    """Hand finished torrents of our category to the renamer. Returns how many."""
    s = _s()
    done, incoming = s["torrent_done"], s["torrent_incoming"]
    stop_seeding = bool(s.get("qbit_stop_seeding"))
    os.makedirs(done, exist_ok=True)
    handed = 0

    torrents = _torrents(s)
    for t in torrents:
        if t.get("progress", 0) < 1 or t.get("state") in _BUSY_STATES:
            continue
        if IMPORTED_TAG in _tags(t):
            continue  # already handed over, still seeding
        src = t.get("content_path") or os.path.join(t.get("save_path", ""), t.get("name", ""))
        if not os.path.exists(src):
            # Usually a path mismatch: qBittorrent and AniWatcher must mount
            # the downloads folder at the same place. Leave the torrent alone.
            log.warning(f"Finished torrent not found at {src} — is the downloads folder "
                        f"mounted at the same path in both containers?")
            continue

        if not stop_seeding:
            try:
                dest = _link_into_done(src, done)
            except OSError as e:
                log.error(f"Could not hand {src} to {done}: {e}")
                continue
            _client.call("POST", "/torrents/addTags", data={"hashes": t["hash"], "tags": IMPORTED_TAG})
            log.info(f"Imported from qBittorrent (still seeding): {t.get('name')} → {dest}")
            handed += 1
            continue

        _client.call("POST", "/torrents/delete", data={"hashes": t["hash"], "deleteFiles": "false"})
        try:
            dest = _move_into_done(src, done)
            log.info(f"Imported from qBittorrent: {t.get('name')} → {dest}")
            handed += 1
        except OSError as e:
            # The torrent is gone from qBittorrent but the files are still in
            # incoming; the sweep below retries them on a later pass.
            log.error(f"Could not move {src} into {done}: {e}")

    # Stop-seeding only: anything in incoming that no torrent accounts for, and
    # that has sat there a while, is a move that failed after its torrent was
    # removed — or a file dropped in by hand. Hand it on too. (While seeding,
    # every file has a torrent, and one the user removed later is theirs.)
    if stop_seeding and os.path.isdir(incoming):
        known = set()
        # Every torrent qBittorrent has, not just ours: a renamed category must
        # not make a live download look like a leftover.
        for t in _client.call("GET", "/torrents/info").json():
            for p in (t.get("content_path"), os.path.join(t.get("save_path", ""), t.get("name", ""))):
                if p:
                    known.add(os.path.realpath(p))
        now = time.time()
        for name in os.listdir(incoming):
            path = os.path.join(incoming, name)
            # qBittorrent can name unfinished files "<name>.!qB"; those are
            # always a live download, however long it has stalled.
            if name.endswith(".!qB") or os.path.realpath(path) in known:
                continue
            if now - os.path.getmtime(path) < _ORPHAN_AGE:
                continue
            try:
                dest = _move_into_done(path, done)
                log.info(f"Moved leftover {name} from incoming → {dest}")
                handed += 1
            except OSError as e:
                log.error(f"Could not move leftover {path}: {e}")
    return handed


def import_loop() -> None:
    """Background thread: hand finished qBittorrent downloads to the renamer."""
    log.info("qBittorrent importer started")
    while True:
        s = _s()
        if s.get("torrent_client") == "qbittorrent":
            try:
                import_completed()
            except (requests.RequestException, QbitError, OSError) as e:
                log.error(f"qBittorrent importer: {e}")
        time.sleep(int(s.get("watch_interval", 60)))
