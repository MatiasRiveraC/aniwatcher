import re
import logging

import feedparser
import requests

from config import NYAA_RSS, NYAA_SEARCH, NYAA_SEARCH_PAGE
from utils.parsing import (
    BATCH_WORDS, episode_marker, episode_range, extract_episode_number, extract_season,
    is_special, release_group, season_in_name, show_name, title_matches,
)

log = logging.getLogger(__name__)

DUAL_AUDIO_MARKERS = re.compile(
    r'dual.?audio|multi.?audio|\bDUAL\b|english.?dub|\bDUB\b|\[English.?Dub\]',
    re.IGNORECASE
)
RES_1080 = re.compile(r'1080p?', re.IGNORECASE)
RES_720  = re.compile(r'720p?',  re.IGNORECASE)


def _get_preferred_groups_re() -> re.Pattern:
    """Build preferred-groups regex from saved settings (or defaults)."""
    from data import get_settings
    groups_str = get_settings().get("preferred_groups", "SubsPlease,Erai-raws,NC-Raws,EMBER")
    escaped = [re.escape(g.strip()) for g in groups_str.split(",") if g.strip()]
    pattern = "|".join(f"\\[{g}\\]" for g in escaped)
    return re.compile(pattern, re.IGNORECASE) if pattern else re.compile(r'(?!)', re.IGNORECASE)


def _get_preferred_resolution() -> str:
    from data import get_settings
    return get_settings().get("preferred_resolution", "1080")


def parse_size_mb(size_str: str) -> float:
    if not size_str or size_str == '?':
        return 9999.0
    m = re.match(r'([\d.]+)\s*(GiB|MiB|GB|MB)', size_str, re.IGNORECASE)
    if not m:
        return 9999.0
    val, unit = float(m.group(1)), m.group(2).upper()
    return val * 1024 if unit in ('GIB', 'GB') else val


def audio_score(title: str) -> int:
    if DUAL_AUDIO_MARKERS.search(title):
        return 0
    if _get_preferred_groups_re().search(title):
        return 3
    return 2


def res_score(title: str) -> int:
    if RES_1080.search(title): return 2
    if RES_720.search(title):  return 1
    return 0


def _filter_by_resolution(results: list) -> list:
    """Filter results to preferred resolution. Returns unfiltered list if none match."""
    preferred = _get_preferred_resolution()
    if preferred == "any":
        return results
    if preferred == "1080":
        filtered = [r for r in results if RES_1080.search(r["title"])]
    elif preferred == "720":
        filtered = [r for r in results if RES_1080.search(r["title"]) or RES_720.search(r["title"])]
    else:
        return results
    if not filtered:
        log.warning(f"No {preferred}p results found — skipping (strict resolution mode)")
    return filtered


def release_sort_key(r: dict):
    return (
        audio_score(r["title"]),
        res_score(r["title"]),
        -parse_size_mb(r.get("size", "?")),
        r["seeders"],
    )


def _parse_feed(url: str) -> list:
    feed = feedparser.parse(url)
    results = []
    for entry in feed.entries:
        seeders = int(entry.get("nyaa_seeders", 0))
        cat     = entry.get("nyaa_category", "")
        title   = entry.title
        if cat.startswith("Anime") and "raw" not in title.lower():
            results.append({
                "title":       title,
                "link":        entry.link,
                "seeders":     seeders,
                "size":        entry.get("nyaa_size", "?"),
                "date":        entry.get("published", ""),
                "audio_score": audio_score(title),
            })
    return results


def search_nyaa(title: str, by_seeders: bool = False) -> list:
    """Newest first (for polling new episodes), or most seeded first (for the search box)."""
    url     = (NYAA_SEARCH if by_seeders else NYAA_RSS).format(query=requests.utils.quote(title))
    results = _parse_feed(url)
    results = _filter_by_resolution(results)
    if by_seeders:
        # Dead torrents last; among live ones the usual preferences, then seeders.
        results.sort(key=lambda r: (r["seeders"] > 0, audio_score(r["title"]), res_score(r["title"]), r["seeders"]),
                     reverse=True)
    else:
        results.sort(key=release_sort_key, reverse=True)
    return results


def _res_ok(title: str) -> bool:
    """At the preferred resolution (or better)."""
    pref = _get_preferred_resolution()
    if pref == "1080":
        return bool(RES_1080.search(title))
    if pref == "720":
        return bool(RES_1080.search(title) or RES_720.search(title))
    return True


def full_sort_key(r: dict):
    """Ranking for a finished show, where a dead torrent never completes: not
    a partial batch, the preferred resolution, enough seeders to finish, a
    batch known to be complete, then the usual audio/resolution preferences
    and more seeders."""
    return (
        r.get("coverage") != "partial",
        _res_ok(r["title"]),
        r["seeders"] >= 5,
        r["seeders"] > 0,
        r.get("coverage") == "complete",
        audio_score(r["title"]),
        res_score(r["title"]),
        r["seeders"],
    )


def _is_batch(r: dict) -> bool:
    t = r["title"]
    if episode_range(t) or BATCH_WORDS.search(t):
        return True
    # A big release with no episode number is a season pack ("[BD 1080p]").
    return episode_marker(t) is None and parse_size_mb(r.get("size", "?")) >= 1500


def _episode(r: dict, names, season: int):
    """Episode number of a single-episode release; a trailing bare number
    ("Show 05") counts unless it is the season ("Genshiken 2")."""
    ep = episode_marker(r["title"])
    if ep is None:
        tail = re.search(r'\s(\d{1,4})(?:v\d)?\s*$', show_name(r["title"]))
        if tail and season_in_name(r["title"], names) != season:
            ep = int(tail.group(1))
    return ep


def search_nyaa_full(title: str, season: int, names=(), total_episodes: int | None = None,
                     start_episode: int | None = None):
    """Every release of one season of a show, as (batches, episodes).

    Searches under each known name (romaji, English, …) sorted by seeders, and
    keeps only releases whose name is the show's — not a sequel or a show with
    a similar name — and whose season is the one asked for. Each result gets
    `batch`, `group`, `ep_num`/`range` and, for batches, `coverage` against
    the episode count: "complete", "partial" or "unknown".
    """
    names = [n for n in dict.fromkeys([title, *names]) if n and n.strip()]
    season_str = f"S{season:02d}" if season > 1 else ""

    queries = []
    for n in names:
        queries.append((f"{n} {season_str}".strip(), 3))
        queries.append((f"{n} {season_str} batch".strip(), 1))
        if season > 1:
            queries.append((n, 2))               # sequels named "Show 2", "Show Season 2", …

    seen, found = set(), []
    for q, pages in queries:
        for page in range(1, pages + 1):
            results = _parse_feed(NYAA_SEARCH_PAGE.format(query=requests.utils.quote(q), page=page))
            for r in results:
                if r["link"] not in seen:
                    seen.add(r["link"])
                    found.append(r)
            if len(results) < 70:
                break

    batches, ep_map, rejected = [], {}, 0
    for r in found:
        t = r["title"]
        if not title_matches(t, names, season) or is_special(t):
            rejected += 1
            continue
        batch = _is_batch(r)
        s = extract_season(t)
        if s is None:
            s2 = season_in_name(t, names)
            if s2 and (batch or episode_marker(t) is not None or s2 == season):
                s = s2
        if (s if s is not None else 1) != season:              # S00 = specials
            rejected += 1
            continue
        r["group"] = release_group(t)
        r["batch"] = batch
        if batch:
            rng = episode_range(t)
            r["range"] = list(rng) if rng else None
            first = start_episode or 1
            if rng and total_episodes:
                r["coverage"] = "complete" if rng[0] <= first and rng[1] >= total_episodes else "partial"
            else:
                r["coverage"] = "unknown"
            batches.append(r)
            continue
        ep = _episode(r, names, season)
        if ep is None or (total_episodes and ep > total_episodes):
            continue
        r["ep_num"] = ep
        ep_map.setdefault(ep, []).append(r)

    # A finished show may have no release at the preferred resolution at all,
    # so here it ranks first instead of filtering the rest out.
    batches.sort(key=full_sort_key, reverse=True)

    episodes = _pick_episodes(ep_map)
    log.info(f"Full season search '{title}' S{season} ({len(names)} names, {len(found)} results, "
             f"{rejected} other shows/seasons): {len(batches)} batches, {len(episodes)} episodes")
    return batches, episodes


def show_names(entry: dict) -> list:
    """Every name a watchlist entry's show is released under."""
    return [n for n in dict.fromkeys([
        entry.get("search_title"), entry.get("title"), entry.get("title_romaji"),
        entry.get("title_english"), *(entry.get("title_synonyms") or []),
    ]) if n and n.strip()]


def search_entry(entry: dict):
    names = show_names(entry)
    return search_nyaa_full(names[0], entry.get("season", 1), names[1:],
                            entry.get("total_episodes"), entry.get("start_episode"))


def _pick_episodes(ep_map: dict) -> list:
    """One release per episode, from as few groups as possible: the group with
    the most live episodes first, gaps filled by the best of the rest."""
    for ep, rs in ep_map.items():
        ep_map[ep] = [r for r in rs if _res_ok(r["title"])] or rs
    counts = {}
    for rs in ep_map.values():
        for g in {r["group"] for r in rs if r["seeders"] > 0 and _res_ok(r["title"])}:
            counts[g] = counts.get(g, 0) + 1
    picked = []
    for ep in sorted(ep_map):
        rs = sorted(ep_map[ep], key=lambda r: (counts.get(r["group"], 0) if r["seeders"] > 0 else -1,
                                                full_sort_key(r)), reverse=True)
        if rs:
            picked.append(rs[0])
    return picked
