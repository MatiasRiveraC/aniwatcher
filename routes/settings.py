import os

from flask import Blueprint, jsonify, request

from data import get_settings, save_settings, DEFAULT_SETTINGS, SECRET_KEYS, locked_keys
from services.library import inside
from services.metadata import inspect_file, strip_mkv_title

bp = Blueprint("settings", __name__)


def _safe_path(path: str) -> str | None:
    """Return realpath if it's inside anime_base, else None."""
    return inside(path, get_settings().get("anime_base", ""))


def _public(settings: dict) -> dict:
    """Settings as the browser may see them: passwords blanked, locks listed."""
    out = {k: ("" if k in SECRET_KEYS else v) for k, v in settings.items()}
    out["_secrets_set"] = [k for k in SECRET_KEYS if settings.get(k)]
    out["_locked"] = list(locked_keys())
    return out


@bp.route("/api/settings", methods=["GET"])
def get_settings_route():
    return jsonify(_public(get_settings()))


@bp.route("/api/settings", methods=["POST"])
def save_settings_route():
    body = request.get_json(force=True, silent=True) or {}
    current = get_settings()

    # Merge and coerce types
    for key, default in DEFAULT_SETTINGS.items():
        if key in body:
            val = body[key]
            # A blank password field means "unchanged": the form never sees it.
            if key in SECRET_KEYS and val in ("", None):
                continue
            if key in locked_keys():
                continue
            try:
                if isinstance(default, bool):
                    # Accept bool, "true"/"false" strings, 0/1
                    if isinstance(val, bool):
                        pass
                    elif isinstance(val, str):
                        val = val.lower() in ("true", "1", "yes", "on")
                    else:
                        val = bool(val)
                elif isinstance(default, int):
                    val = int(val)
                elif isinstance(default, float):
                    val = float(val)
                else:
                    val = str(val)
            except (ValueError, TypeError):
                val = current[key]
            current[key] = val

    save_settings(current)
    return jsonify({"ok": True, "settings": _public(current)})


@bp.route("/api/browse-library", methods=["GET"])
def browse_library():
    """
    Lazily list one level of the anime library.
    ?path= omitted → anime_base root
    ?path=<dir>    → contents of that directory (must be inside anime_base)
    Returns folders and .mkv files sorted alphabetically.
    """
    raw_path = request.args.get("path", "").strip()
    anime_base = get_settings().get("anime_base", "/media/anime")

    if not raw_path:
        target = anime_base
    else:
        target = _safe_path(raw_path)
        if not target:
            return jsonify({"error": "invalid path"}), 400

    if not os.path.isdir(target):
        return jsonify({"error": "directory not found", "path": target}), 404

    items = []
    try:
        for name in sorted(os.listdir(target), key=str.lower):
            full = os.path.join(target, name)
            if os.path.isdir(full):
                items.append({"name": name, "path": full, "type": "dir"})
            elif name.lower().endswith(".mkv"):
                items.append({"name": name, "path": full, "type": "file"})
    except PermissionError:
        return jsonify({"error": "permission denied"}), 403

    return jsonify({"path": target, "items": items})


@bp.route("/api/inspect-file", methods=["GET"])
def inspect_file_route():
    """Return embedded metadata for a single MKV file."""
    raw_path = request.args.get("path", "").strip()
    if not raw_path:
        return jsonify({"error": "path required"}), 400
    target = _safe_path(raw_path)
    if not target:
        return jsonify({"error": "invalid path"}), 400
    return jsonify(inspect_file(target))


@bp.route("/api/clean-file", methods=["POST"])
def clean_file_route():
    """Strip title metadata from a single MKV file."""
    raw_path = (request.get_json(force=True, silent=True) or {}).get("path", "")
    if not raw_path:
        return jsonify({"error": "path required"}), 400
    target = _safe_path(raw_path)
    if not target:
        return jsonify({"error": "invalid path"}), 400
    ok = strip_mkv_title(target)
    return jsonify({"ok": ok})
