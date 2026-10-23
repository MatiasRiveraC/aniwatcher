import os
import shutil
import queue
import logging
import threading

from flask import Blueprint, render_template, jsonify, Response, request

from config import VIDEO_EXTS
from data import load_data, get_settings
from services.library import inside
from services.metadata import clean_library, mkvpropedit_available
from services.torrents import client_name

bp  = Blueprint("system", __name__)
log = logging.getLogger(__name__)

log_queue = queue.Queue(maxsize=500)


class _QueueHandler(logging.Handler):
    def emit(self, record):
        try:
            log_queue.put_nowait(self.format(record))
        except queue.Full:
            pass


def setup_log_handler():
    handler = _QueueHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(handler)


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/api/status")
def status():
    data   = load_data()
    unread = sum(1 for n in data.get("notifications", []) if not n.get("read"))
    return jsonify({
        "watchlist_count":      len(data["watchlist"]),
        "downloaded":           len(data["downloaded"]),
        "renamed":              len(data.get("renamed", [])),
        "unread_notifications": unread,
        "torrent_client":       client_name(),
    })


@bp.route("/api/logs")
def stream_logs():
    def generate():
        yield "data: -- Log stream started --\n\n"
        while True:
            try:
                msg = log_queue.get(timeout=15)
                msg = msg.replace("\n", " ").replace("\r", "")
                yield f"data: {msg}\n\n"
            except queue.Empty:
                yield "data: \n\n"  # keepalive
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


_clean_lock   = threading.Lock()
_clean_status = {"running": False, "last": None}


@bp.route("/api/clean-metadata", methods=["POST"])
def clean_metadata():
    if not mkvpropedit_available():
        return jsonify({"ok": False, "error": "mkvpropedit not installed"}), 503
    if not _clean_lock.acquire(blocking=False):
        return jsonify({"ok": False, "error": "already running"}), 409

    anime_base = get_settings().get("anime_base", "/media/anime")

    def _run():
        try:
            _clean_status["running"] = True
            stats = clean_library(anime_base)
            _clean_status["last"] = stats
        finally:
            _clean_status["running"] = False
            _clean_lock.release()

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "message": f"Cleaning metadata in {anime_base}…"})


@bp.route("/api/clean-metadata/status", methods=["GET"])
def clean_metadata_status():
    return jsonify(_clean_status)


def _safe_completed_path(path: str) -> str | None:
    """Return realpath only if it's strictly inside TORRENT_DONE."""
    return inside(path, get_settings().get("torrent_done", "/downloads/completed"))


@bp.route("/api/completed-files", methods=["GET"])
def completed_files():
    TORRENT_DONE = get_settings().get("torrent_done", "/downloads/completed")
    result = {"dirs": [], "files": [], "path": TORRENT_DONE}
    if not os.path.isdir(TORRENT_DONE):
        return jsonify(result)
    for name in sorted(os.listdir(TORRENT_DONE)):
        full = os.path.join(TORRENT_DONE, name)
        if os.path.isdir(full):
            files = [f for f in os.listdir(full) if os.path.splitext(f)[1].lower() in VIDEO_EXTS]
            size  = sum(os.path.getsize(os.path.join(full, f)) for f in files if os.path.isfile(os.path.join(full, f)))
            result["dirs"].append({
                "name": name, "path": full,
                "files": len(files), "size_mb": round(size / 1024 / 1024, 1),
            })
        elif os.path.splitext(name)[1].lower() in VIDEO_EXTS | {".torrent"}:
            size = os.path.getsize(full)
            result["files"].append({
                "name": name, "path": full,
                "size_mb": round(size / 1024 / 1024, 1),
            })
    return jsonify(result)


@bp.route("/api/completed-files/dir", methods=["GET"])
def completed_dir_contents():
    """List files inside a completed sub-directory."""
    raw = request.args.get("path", "")
    target = _safe_completed_path(raw)
    if not target or not os.path.isdir(target):
        return jsonify({"error": "invalid path"}), 400
    items = []
    for name in sorted(os.listdir(target)):
        full = os.path.join(target, name)
        if os.path.isfile(full):
            items.append({
                "name":    name,
                "path":    full,
                "size_mb": round(os.path.getsize(full) / 1024 / 1024, 1),
                "ext":     os.path.splitext(name)[1].lower(),
            })
    return jsonify({"items": items})


@bp.route("/api/completed-files/delete", methods=["POST"])
def delete_completed():
    """Delete a file or directory inside TORRENT_DONE."""
    raw = (request.get_json(force=True, silent=True) or {}).get("path", "")
    target = _safe_completed_path(raw)
    if not target:
        return jsonify({"ok": False, "error": "invalid path"}), 400
    if not os.path.exists(target):
        return jsonify({"ok": False, "error": "not found"}), 404
    try:
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
        log.info(f"Deleted completed item: {target}")
        return jsonify({"ok": True})
    except Exception as e:
        log.error(f"Delete failed {target}: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500
