from flask import Blueprint, jsonify

from data import load_data, save_data

bp = Blueprint("notifications", __name__)


@bp.route("/api/notifications", methods=["GET"])
def get_notifications():
    data = load_data()
    return jsonify(data.get("notifications", []))


@bp.route("/api/notifications/read", methods=["POST"])
def mark_notifications_read():
    data = load_data()
    for n in data.get("notifications", []):
        n["read"] = True
    save_data(data)
    return jsonify({"ok": True})
