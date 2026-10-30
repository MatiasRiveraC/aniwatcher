import threading
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

from data import load_data, save_data
from services.nyaa import search_nyaa

bp = Blueprint("downloads", __name__)


def _iso_utc(date: str) -> str:
    """Stored dates are naive server-local time; return ISO UTC so the browser can
    group by its own day. '' when missing or unreadable."""
    try:
        return datetime.fromisoformat(date).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return ""


@bp.route("/api/downloaded", methods=["GET"])
def get_downloaded():
    data   = load_data()
    result = []
    for d in data.get("downloaded", []):
        if isinstance(d, str):
            result.append({"url": d, "title": d, "date": ""})
        else:
            result.append({**d, "date": _iso_utc(d.get("date", ""))})
    return jsonify(result)


@bp.route("/api/downloaded/delete", methods=["POST"])
def delete_downloaded():
    urls   = request.json.get("urls", [])
    data   = load_data()
    before = len(data["downloaded"])
    data["downloaded"] = [
        d for d in data["downloaded"]
        if (d["url"] if isinstance(d, dict) else d) not in urls
    ]
    save_data(data)
    return jsonify({"ok": True, "removed": before - len(data["downloaded"])})


@bp.route("/api/search")
def api_search():
    q = request.args.get("q", "")
    return jsonify(search_nyaa(q)[:10] if q else [])


@bp.route("/api/poll", methods=["POST"])
def manual_poll():
    from services.poller import do_poll
    threading.Thread(target=do_poll, daemon=True).start()
    return jsonify({"ok": True})
