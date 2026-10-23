import re
import time
import logging
import threading
from datetime import datetime

from data import get_settings
from data import load_data, save_data
from services.mal import refresh_mal
from services.nyaa import search_nyaa, search_nyaa_full, release_sort_key
from services.library import episode_exists_on_disk
from services.torrents import add_torrent
from utils.parsing import extract_episode_number, extract_season

log = logging.getLogger(__name__)


# ── Notification helpers ───────────────────────────────────────────────────────

def push_notification(data: dict, message: str, kind: str = "info"):
    data.setdefault("notifications", [])
    data["notifications"].append({
        "id":      int(time.time() * 1000),
        "message": message,
        "kind":    kind,
        "time":    str(datetime.now()),
        "read":    False,
    })


def check_completion(entry: dict, data: dict):
    """Push a notification when all expected episodes have been grabbed."""
    total = entry.get("total_episodes")
    if not total:
        return
    grabbed_eps = set()
    for g in entry.get("episodes_grabbed", []):
        if g.get("ep") and g["ep"] != "batch":
            grabbed_eps.add(g["ep"])
    if total < len(grabbed_eps):
        log.warning(
            f"check_completion: total_episodes={total} < grabbed={len(grabbed_eps)} "
            f"for '{entry['title']}' — skipping (bad MAL data)"
        )
        return
    if len(grabbed_eps) >= total:
        title  = entry["title"]
        season = entry.get("season", 1)
        msg    = f"✓ {title} Season {season} is complete — all {total} episodes grabbed!"
        log.info(msg)
        push_notification(data, msg, "success")
        entry["all_grabbed"] = True


# ── Poller ─────────────────────────────────────────────────────────────────────

def do_poll():
    data    = load_data()
    changed = False
    for entry in data["watchlist"]:
        if not entry.get("active", True):
            continue
        if entry.get("mode") == "complete":
            continue

        title        = entry["title"]
        search_title = entry.get("search_title") or title
        season       = entry.get("season", 1)

        if entry.get("airing_status") != "FINISHED":
            if refresh_mal(entry):
                changed = True
            grabbed_count = len({g["ep"] for g in entry.get("episodes_grabbed", []) if g.get("ep") and g["ep"] != "batch"})
            total = entry.get("total_episodes") or 0
            if entry.get("all_grabbed") and total > grabbed_count:
                log.info(f"MAL corrected total_episodes to {total} for '{title}' (grabbed {grabbed_count}) — clearing all_grabbed")
                entry["all_grabbed"] = False
                changed = True

        if entry.get("all_grabbed"):
            continue

        log.info(f"Polling nyaa: {search_title} S{season:02d} (folder: {title})")

        query   = search_title if season == 1 else f"{search_title} S{season:02d}"
        results = search_nyaa(query)

        start_ep = entry.get("start_episode")
        for r in results:
            key = r["link"]
            ep  = extract_episode_number(r["title"])

            detected_season = extract_season(r["title"])
            if detected_season and detected_season != season:
                continue

            # With start_episode set: skip anything with no parseable episode number
            # (specials, movies, fan letters) AND anything below the threshold.
            if start_ep and (ep is None or ep < start_ep):
                continue

            dl_urls = {d["url"] if isinstance(d, dict) else d for d in data["downloaded"]}
            if key in dl_urls:
                continue

            s = detected_season or season
            if ep and episode_exists_on_disk(title, s, ep):
                log.info(f"Episode {ep} already on disk for {title}, skipping")
                data["downloaded"].append(key)
                changed = True
                continue

            if ep and any(g.get("ep") == ep for g in entry.get("episodes_grabbed", [])):
                continue

            ok = add_torrent(r["link"])
            if ok:
                data["downloaded"].append({"url": key, "title": r["title"], "date": str(datetime.now())})
                entry.setdefault("episodes_grabbed", [])
                entry["episodes_grabbed"].append({
                    "ep":    ep,
                    "title": r["title"],
                    "date":  str(datetime.now()),
                })
                check_completion(entry, data)
                changed = True
                audio = {2: 'sub', 1: 'unknown', 0: 'dual'}.get(r.get('audio_score', 1), '?')
                log.info(f"Queued {title} ep {ep} [{audio}]: {r['title'][:60]}")
                break

    if changed:
        save_data(data)


def poll_loop():
    while True:
        try:
            do_poll()
        except Exception as e:
            log.error(f"Poll error: {e}")
        time.sleep(get_settings().get("poll_interval", 900))


# ── Full season download ───────────────────────────────────────────────────────

def do_full_season(entry_id: int):
    data  = load_data()
    entry = next((e for e in data["watchlist"] if e["id"] == entry_id), None)
    if not entry:
        return {"ok": False, "error": "not found"}

    title        = entry["title"]
    search_title = entry.get("search_title") or title
    season       = entry.get("season", 1)
    log.info(f"Full season download: {title} S{season} (searching: {search_title})")

    batches, episodes = search_nyaa_full(search_title, season)
    queued     = 0
    used_batch = False

    for b in sorted(batches, key=lambda x: x["seeders"], reverse=True):
        if b["link"] in data["downloaded"]:
            continue
        if add_torrent(b["link"]):
            data["downloaded"].append({"url": b["link"], "title": b["title"], "date": str(datetime.now())})
            entry.setdefault("episodes_grabbed", [])
            entry["episodes_grabbed"].append({"ep": "batch", "title": b["title"], "date": str(datetime.now())})
            queued += 1
            used_batch = True
            break

    start_ep = entry.get("start_episode")
    if not used_batch:
        for r in episodes:
            ep = extract_episode_number(r["title"])
            s  = extract_season(r["title"]) or season

            if start_ep and (ep is None or ep < start_ep):
                log.info(f"  → skipping ep {ep} (below/missing start_episode={start_ep})")
                continue

            log.info(f"Full season candidate: ep={ep} s={s} title={r['title'][:60]}")

            if r["link"] in data["downloaded"]:
                log.info("  → skipping (already in downloaded list)")
                continue

            if episode_exists_on_disk(title, s, ep):
                log.info("  → skipping (already on disk)")
                data["downloaded"].append(r["link"])
                continue

            ok = add_torrent(r["link"])
            log.info(f"  → add_torrent result: {ok}")
            if ok:
                data["downloaded"].append(r["link"])
                entry.setdefault("episodes_grabbed", [])
                entry["episodes_grabbed"].append({
                    "ep": ep, "title": r["title"], "date": str(datetime.now()),
                })
                queued += 1

    check_completion(entry, data)
    save_data(data)
    return {"ok": True, "queued": queued, "used_batch": used_batch, "title": title, "season": season}
