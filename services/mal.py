import re
import logging

import requests

from config import MAL_API, MAL_CLIENT_ID

log = logging.getLogger(__name__)


def fetch_mal_info(title: str, season: int) -> dict:
    """Query MyAnimeList for series info including split-cour detection."""
    headers = {"X-MAL-CLIENT-ID": MAL_CLIENT_ID}
    try:
        query = f"{title} Season {season}" if season > 1 else title
        resp = requests.get(
            f"{MAL_API}/anime",
            headers=headers,
            params={"q": query, "limit": 8, "fields": "id,title,alternative_titles,num_episodes,status,related_anime"},
            timeout=10
        )
        resp.raise_for_status()
        results = resp.json().get("data", [])
        if not results:
            resp = requests.get(f"{MAL_API}/anime", headers=headers,
                params={"q": title, "limit": 8, "fields": "id,title,alternative_titles,num_episodes,status,related_anime"},
                timeout=10)
            results = resp.json().get("data", [])
        if not results:
            log.warning(f"MAL: no results for '{title}'")
            return {}

        def word_overlap(a: str, b: str) -> int:
            wa = set(w for w in re.split(r'\W+', a.lower()) if len(w) > 2)
            wb = set(w for w in re.split(r'\W+', b.lower()) if len(w) > 2)
            return len(wa & wb)

        def match_score(node):
            eng  = (node.get("alternative_titles", {}).get("en") or "").lower()
            rom  = (node.get("title") or "").lower()
            syns = [s.lower() for s in node.get("alternative_titles", {}).get("synonyms", [])]
            t    = title.lower()
            overlap = max(
                word_overlap(t, eng),
                word_overlap(t, rom),
                *(word_overlap(t, s) for s in syns) if syns else (0,)
            )
            exact = int(t in (eng, rom) or any(t == s for s in syns))
            season_markers = [f"season {season}", f"s{season:02d}", f"{season}nd season",
                              f"{season}rd season", f"{season}th season", f"{season}st season"]
            season_match = int(any(m in rom or m in eng for m in season_markers)) if season > 1 else 1
            status = node.get("status", "")
            status_score = {"currently_airing": 2, "not_yet_aired": 1}.get(status, 0)
            return (exact, overlap, season_match, status_score)

        scored = [(match_score(item.get("node", {})), item.get("node", {})) for item in results]
        scored.sort(key=lambda x: x[0], reverse=True)
        match = scored[0][1] if scored else results[0].get("node", {})

        detail = requests.get(
            f"{MAL_API}/anime/{match['id']}",
            headers=headers,
            params={"fields": "id,title,alternative_titles,num_episodes,status,related_anime"},
            timeout=10
        ).json()

        total_eps    = detail.get("num_episodes") or 0
        overall_stat = detail.get("status") or ""
        eng_title    = (detail.get("alternative_titles") or {}).get("en") or ""
        rom_title    = detail.get("title") or ""
        # Other names it is released under; Latin-script ones only, nyaa titles are.
        synonyms     = [s for s in (detail.get("alternative_titles") or {}).get("synonyms", [])
                        if s and s.isascii()]
        display      = eng_title or rom_title or title

        status_map = {"finished_airing": "FINISHED", "currently_airing": "RELEASING", "not_yet_aired": "NOT_YET_RELEASED"}
        normalized = status_map.get(overall_stat, overall_stat.upper())
        parts = [{"title": display, "episodes": detail.get("num_episodes"), "status": normalized}]
        log.info(f"MAL: '{title}' → {total_eps} eps, status={normalized}")
        return {
            "total_episodes": total_eps if total_eps > 0 else None,
            "status":         normalized,
            "mal_id":         detail.get("id"),
            "title":          display,
            "title_romaji":   rom_title,
            "title_english":  eng_title,
            "title_synonyms": synonyms,
            "parts":          parts,
        }
    except Exception as e:
        log.error(f"MAL error for '{title}': {e}")
        return {}


def refresh_mal(entry: dict) -> bool:
    """Re-fetch MAL info for an entry and update it in place. Returns True if changed."""
    info = fetch_mal_info(entry["title"], entry.get("season", 1))
    if not info:
        return False
    changed = (entry.get("total_episodes") != info.get("total_episodes") or
               entry.get("airing_status")  != info.get("status"))
    entry["total_episodes"] = info.get("total_episodes")
    entry["airing_status"]  = info.get("status")
    entry["mal_id"]         = info.get("mal_id")
    entry["anilist_parts"]  = info.get("parts", [])
    entry["title_romaji"]   = info.get("title_romaji", "")
    entry["title_english"]  = info.get("title_english", "")
    entry["title_synonyms"] = info.get("title_synonyms", [])
    return changed
