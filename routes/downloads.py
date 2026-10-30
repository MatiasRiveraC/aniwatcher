import threading

import requests

from flask import Blueprint, request, jsonify

from data import load_data, save_data
from services.nyaa import search_nyaa
from services.nyaa_details import release_details

bp = Blueprint("downloads", __name__)


@bp.route("/api/downloaded", methods=["GET"])
def get_downloaded():
    data   = load_data()
    result = []
    for d in data.get("downloaded", []):
        if isinstance(d, str):
            result.append({"url": d, "title": d, "date": ""})
        else:
            result.append(d)
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
    return jsonify(search_nyaa(q, by_seeders=True)[:10] if q else [])


@bp.route("/api/poll", methods=["POST"])
def manual_poll():
    from services.poller import do_poll
    threading.Thread(target=do_poll, daemon=True).start()
    return jsonify({"ok": True})


@bp.route("/api/nyaa/<int:view_id>")
def api_release_details(view_id):
    """Description, file list and comments of a nyaa release, for the picker."""
    try:
        return jsonify(release_details(view_id))
    except requests.RequestException as e:
        return jsonify({"error": f"Could not read nyaa.si/view/{view_id}: {e}"}), 502
