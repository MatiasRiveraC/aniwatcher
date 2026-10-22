import os
import re
import time
import threading
from datetime import datetime

from flask import Blueprint, request, jsonify, current_app

from data import load_data, save_data, get_settings
from services.mal import fetch_mal_info
from services.nyaa import search_nyaa_full, release_sort_key
from services.metadata import inspect_series, strip_mkv_title
from services.deluge import add_torrent_to_deluge, episode_exists_on_disk
from services.poller import do_full_season
from utils.parsing import extract_episode_number

bp = Blueprint("watchlist", __name__)


@bp.route("/api/watchlist", methods=["GET"])
def get_watchlist():
    return jsonify(load_data()["watchlist"])


@bp.route("/api/watchlist", methods=["POST"])
def add_anime():
    body  = request.json
    title = body.get("title", "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400

    data       = load_data()
    season_num = int(body.get("season", 1))
    if any(e["title"].lower() == title.lower() and e.get("season", 1) == season_num
           for e in data["watchlist"]):
        return jsonify({"error": "already in watchlist"}), 409

    start_ep_raw = body.get("start_episode")
    start_ep = int(start_ep_raw) if start_ep_raw and str(start_ep_raw).strip() else None

    entry = {
        "id":               int(time.time() * 1000),
        "title":            title,
        "search_title":     body.get("search_title", "").strip() or title,
        "season":           season_num,
        "active":           True,
        "mode":             body.get("mode", "ongoing"),
        "added":            str(datetime.now()),
        "episodes_grabbed": [],
        "total_episodes":   None,
        "airing_status":    None,
        "anilist_id":       None,
        "anilist_parts":    [],
        "all_grabbed":      False,
        "start_episode":    start_ep,
    }

    info = fetch_mal_info(title, entry["season"])
    if info:
        entry["total_episodes"] = info.get("total_episodes")
        entry["airing_status"]  = info.get("status")
        entry["anilist_id"]     = info.get("anilist_id")
        entry["anilist_parts"]  = info.get("parts", [])
        entry["title_romaji"]   = info.get("title_romaji", "")
        entry["title_english"]  = info.get("title_english", "")

    data["watchlist"].append(entry)
    save_data(data)
    return jsonify(entry), 201


@bp.route("/api/watchlist/<int:entry_id>", methods=["PATCH"])
def toggle_anime(entry_id):
    data = load_data()
    for e in data["watchlist"]:
        if e["id"] == entry_id:
            body = request.json or {}
            if "total_episodes" in body:
                e["total_episodes"] = int(body["total_episodes"]) if body["total_episodes"] else None
                e["all_grabbed"] = False
            elif "start_episode" in body:
                e["start_episode"] = int(body["start_episode"]) if body["start_episode"] else None
            else:
                e["active"] = not e.get("active", True)
            save_data(data)
            return jsonify(e)
    return jsonify({"error": "not found"}), 404


@bp.route("/api/watchlist/<int:entry_id>", methods=["DELETE"])
def delete_anime(entry_id):
    data = load_data()
    data["watchlist"] = [e for e in data["watchlist"] if e["id"] != entry_id]
    save_data(data)
    return jsonify({"ok": True})


@bp.route("/api/watchlist/<int:entry_id>/full-season", methods=["POST"])
def full_season(entry_id):
    data  = load_data()
    entry = next((e for e in data["watchlist"] if e["id"] == entry_id), None)
    if not entry:
        return jsonify({"error": "not found"}), 404
    if entry.get("manual_pick"):
        title        = entry["title"]
        search_title = entry.get("search_title") or title
        season       = entry.get("season", 1)
        batches, episodes = search_nyaa_full(search_title, season)
        candidates = sorted(batches + episodes, key=release_sort_key, reverse=True)[:10]
        return jsonify({"ok": True, "manual": True, "candidates": candidates})
    threading.Thread(target=lambda: do_full_season(entry_id), daemon=True).start()
    return jsonify({"ok": True, "message": "Full season search started"})


@bp.route("/api/watchlist/<int:entry_id>/manual-download", methods=["POST"])
def manual_download(entry_id):
    body = request.json
    url  = body.get("url")
    if not url:
        return jsonify({"error": "url required"}), 400
    data  = load_data()
    entry = next((e for e in data["watchlist"] if e["id"] == entry_id), None)
    if not entry:
        return jsonify({"error": "not found"}), 404
    ok = add_torrent_to_deluge(url)
    if ok:
        ep    = extract_episode_number(body.get("title", ""))
        title = body.get("title", url)
        data["downloaded"].append({"url": url, "title": title, "date": str(datetime.now())})
        entry.setdefault("episodes_grabbed", []).append({
            "ep": ep, "title": title, "date": str(datetime.now())
        })
        save_data(data)
        return jsonify({"ok": True})
    return jsonify({"error": "Deluge error"}), 500


@bp.route("/api/watchlist/<int:entry_id>/toggle-manual", methods=["POST"])
def toggle_manual_pick(entry_id):
    data = load_data()
    for e in data["watchlist"]:
        if e["id"] == entry_id:
            e["manual_pick"] = not e.get("manual_pick", False)
            save_data(data)
            return jsonify({"ok": True, "manual_pick": e["manual_pick"]})
    return jsonify({"error": "not found"}), 404


@bp.route("/api/watchlist/<int:entry_id>/scan", methods=["POST"])
def scan_disk(entry_id):
    data  = load_data()
    entry = next((e for e in data["watchlist"] if e["id"] == entry_id), None)
    if not entry:
        return jsonify({"error": "not found"}), 404

    title  = entry["title"]
    season = entry.get("season", 1)
    found_eps = set()
    pattern   = re.compile(rf'S{season:02d}E(\d{{2,4}})', re.IGNORECASE)

    ANIME_BASE = get_settings().get("anime_base", "/media/anime")
    if os.path.isdir(ANIME_BASE):
        clean     = re.sub(r'[<>:"/\\|?*]', '', title).strip().lower()
        words     = [w for w in re.split(r'\W+', clean) if len(w) > 3]
        rom       = entry.get("title_romaji", "").lower()
        eng       = entry.get("title_english", "").lower()
        rom_words = [w for w in re.split(r'\W+', rom) if len(w) > 3]
        eng_words = [w for w in re.split(r'\W+', eng) if len(w) > 3]
        all_words = set(words + rom_words + eng_words)

        for series_dir in os.listdir(ANIME_BASE):
            d_lower    = series_dir.lower()
            matches    = sum(1 for w in all_words if w in d_lower)
            full_match = clean in d_lower or d_lower in clean
            if not full_match and matches < 3:
                continue
            season_path = os.path.join(ANIME_BASE, series_dir, f"Season {season}")
            if not os.path.isdir(season_path):
                continue
            for fname in os.listdir(season_path):
                m = pattern.search(fname)
                if m:
                    found_eps.add(int(m.group(1)))

    existing = {g["ep"] for g in entry.get("episodes_grabbed", []) if isinstance(g.get("ep"), int)}
    new_eps  = found_eps - existing
    for ep in sorted(new_eps):
        entry.setdefault("episodes_grabbed", []).append({
            "ep": ep, "title": "Scanned from disk", "date": str(datetime.now())
        })

    total = entry.get("total_episodes") or 0
    if found_eps and total > 0 and len(found_eps) >= total:
        entry["all_grabbed"] = True

    save_data(data)
    current_app.logger.info(f"Disk scan for '{title}' S{season}: found {len(found_eps)} episodes, added {len(new_eps)} new")
    return jsonify({"ok": True, "found": len(found_eps), "new": len(new_eps), "episodes": sorted(found_eps)})


@bp.route("/api/watchlist/<int:entry_id>/inspect-metadata", methods=["GET"])
def inspect_metadata(entry_id):
    data  = load_data()
    entry = next((e for e in data["watchlist"] if e["id"] == entry_id), None)
    if not entry:
        return jsonify({"error": "not found"}), 404
    anime_base = get_settings().get("anime_base", "/media/anime")
    result = inspect_series(anime_base, entry["title"], entry.get("season", 1))
    return jsonify(result)


@bp.route("/api/watchlist/<int:entry_id>/clean-file", methods=["POST"])
def clean_single_file(entry_id):
    path = (request.json or {}).get("path")
    if not path:
        return jsonify({"error": "path required"}), 400
    ok = strip_mkv_title(path)
    return jsonify({"ok": ok})


@bp.route("/api/watchlist/<int:entry_id>/reset", methods=["POST"])
def reset_history(entry_id):
    data  = load_data()
    entry = next((e for e in data["watchlist"] if e["id"] == entry_id), None)
    if not entry:
        return jsonify({"error": "not found"}), 404

    title   = entry["title"]
    romaji  = entry.get("title_romaji", "")
    english = entry.get("title_english", "")
    before  = len(data["downloaded"])

    keywords = set()
    for t in [title, romaji, english]:
        for w in re.split(r'\W+', t.lower()):
            if len(w) > 3:
                keywords.add(w)

    def url_matches(d):
        url    = d["url"]    if isinstance(d, dict) else d
        dtitle = d.get("title", "") if isinstance(d, dict) else ""
        text   = (url + " " + dtitle).lower()
        return sum(1 for kw in keywords if kw in text) >= 2

    data["downloaded"] = [d for d in data["downloaded"] if not url_matches(d)]
    removed = before - len(data["downloaded"])

    entry["episodes_grabbed"] = []
    entry["all_grabbed"]      = False

    save_data(data)
    current_app.logger.info(f"Reset history for '{title}': cleared {removed} URLs")
    return jsonify({"ok": True, "removed": removed, "title": title})
