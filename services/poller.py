import re
import time
import logging
import threading
from datetime import datetime

from data import get_settings
from data import load_data, save_data
from services.mal import refresh_mal
from services.nyaa import search_nyaa, search_entry
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

def search_titles(entry: dict) -> list:
    """The entry's nyaa searches in the order they are tried. Older entries only have
    `search_title`; `search_titles[0]` is always kept equal to it."""
    return entry.get("search_titles") or [entry.get("search_title") or entry["title"]]


def clean_search_titles(titles, fallback: str) -> list:
    """Strip, drop blanks and repeats (keeping order); never empty."""
    seen, out = set(), []
    for t in titles or []:
        t = str(t).strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out or [fallback]


def _poll_query(entry: dict, search: str) -> str:
    season = entry.get("season", 1)
    return search if season == 1 else f"{search} S{season:02d}"


def check_result(entry: dict, r: dict, dl_urls: set):
    """Decide what the poller does with nyaa result `r` for `entry`.
    Returns (skip, ep): skip is None to grab it, else the reason — "season", "start_ep",
    "downloaded", "on_disk" or "grabbed". Shared by do_poll and preview_poll."""
    season = entry.get("season", 1)
    ep     = extract_episode_number(r["title"])

    detected_season = extract_season(r["title"])
    if detected_season and detected_season != season:
        return "season", ep

    # With start_episode set: skip anything with no parseable episode number
    # (specials, movies, fan letters) AND anything below the threshold.
    start_ep = entry.get("start_episode")
    if start_ep and (ep is None or ep < start_ep):
        return "start_ep", ep

    if r["link"] in dl_urls:
        return "downloaded", ep

    if ep and episode_exists_on_disk(entry["title"], detected_season or season, ep):
        return "on_disk", ep

    if ep and any(g.get("ep") == ep for g in entry.get("episodes_grabbed", [])):
        return "grabbed", ep

    return None, ep


def preview_poll(entry: dict) -> dict:
    """Dry run of do_poll for one entry: each nyaa search in order and what a poll would
    do with its results right now. Grabs nothing and saves nothing."""
    if not entry.get("active", True):
        not_polled = "Paused: the poller skips this series."
    elif entry.get("mode") == "complete":
        not_polled = "Full-season mode: the poller skips this series (use Full season instead)."
    elif entry.get("all_grabbed"):
        not_polled = "All episodes grabbed: the poller skips this series."
    else:
        not_polled = None

    data     = load_data()
    dl_urls  = {d["url"] if isinstance(d, dict) else d for d in data["downloaded"]}
    searches = []
    picked   = False
    queued   = set()  # episodes a poll will grab, so other releases of them get skipped
    for search in search_titles(entry):
        query = _poll_query(entry, search)
        if picked:
            # do_poll stops at the first search that has something to grab
            searches.append({"query": query, "tried": False, "results": []})
            continue
        results = []
        for r in search_nyaa(query):
            skip, ep = check_result(entry, r, dl_urls)
            if skip is None and ep and ep in queued:
                action = "duplicate"
            elif skip is None:
                # do_poll grabs one result per poll; the rest wait for later polls
                action, picked = ("later" if picked else "grab"), True
                if ep:
                    queued.add(ep)
            else:
                action = skip
            results.append({**r, "ep": ep, "action": action})
        searches.append({"query": query, "tried": True, "results": results})
    return {"searches": searches, "not_polled": not_polled}


def do_poll():
    data    = load_data()
    changed = False
    for entry in data["watchlist"]:
        if not entry.get("active", True):
            continue
        if entry.get("mode") == "complete":
            continue

        title = entry["title"]

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

        # Searches are tried in order; the next one only when this one grabs nothing
        grabbed = False
        for search in search_titles(entry):
            query = _poll_query(entry, search)
            log.info(f"Polling nyaa: {query} (folder: {title})")

            for r in search_nyaa(query):
                key = r["link"]
                dl_urls  = {d["url"] if isinstance(d, dict) else d for d in data["downloaded"]}
                skip, ep = check_result(entry, r, dl_urls)

                if skip == "on_disk":
                    log.info(f"Episode {ep} already on disk for {title}, skipping")
                    data["downloaded"].append(key)
                    changed = True
                    continue
                if skip:
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
                    grabbed = True
                    break
            if grabbed:
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

    title  = entry["title"]
    season = entry.get("season", 1)
    log.info(f"Full season download: {title} S{season}")

    batches, episodes = search_entry(entry)
    dl_urls    = {d["url"] if isinstance(d, dict) else d for d in data["downloaded"]}
    queued     = 0
    used_batch = False

    # A batch only if it is known to cover the season, or might (no episode
    # range in its name), and someone is seeding it. A partial batch loses to
    # single episodes. Batches come sorted best first.
    for b in batches:
        if b["coverage"] == "partial" or b["seeders"] == 0 or b["link"] in dl_urls:
            continue
        if add_torrent(b["link"]):
            data["downloaded"].append({"url": b["link"], "title": b["title"], "date": str(datetime.now())})
            entry.setdefault("episodes_grabbed", [])
            entry["episodes_grabbed"].append({"ep": "batch", "title": b["title"], "date": str(datetime.now())})
            log.info(f"  → batch ({b['coverage']}, {b['seeders']} seeders): {b['title'][:80]}")
            queued += 1
            used_batch = True
        break

    start_ep = entry.get("start_episode")
    if not used_batch:
        for r in episodes:
            ep = r["ep_num"]
            if start_ep and ep < start_ep:
                continue
            if r["link"] in dl_urls or r["seeders"] == 0:
                continue
            if episode_exists_on_disk(title, season, ep):
                log.info(f"  → ep {ep} already on disk")
                data["downloaded"].append(r["link"])
                continue
            if add_torrent(r["link"]):
                data["downloaded"].append({"url": r["link"], "title": r["title"], "date": str(datetime.now())})
                entry.setdefault("episodes_grabbed", [])
                entry["episodes_grabbed"].append({"ep": ep, "title": r["title"], "date": str(datetime.now())})
                log.info(f"  → ep {ep} [{r['group'] or 'no group'}]: {r['title'][:80]}")
                queued += 1

    if not queued:
        push_notification(data, f"No live release found for {title} Season {season} — "
                                f"try 🎯 manual pick, or another search title", "warn")
    check_completion(entry, data)
    save_data(data)
    return {"ok": True, "queued": queued, "used_batch": used_batch, "title": title, "season": season}
