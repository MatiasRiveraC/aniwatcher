import re
import logging

import feedparser
import requests

from config import NYAA_RSS, NYAA_SEARCH, NYAA_SEARCH_PAGE
from utils.parsing import extract_episode_number, extract_season

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


def search_nyaa(title: str) -> list:
    url     = NYAA_RSS.format(query=requests.utils.quote(title))
    results = _parse_feed(url)
    results = _filter_by_resolution(results)
    results.sort(key=release_sort_key, reverse=True)
    return results


def search_nyaa_full(title: str, season: int):
    """Search nyaa for all available episodes of a season, paginating up to 5 pages."""
    season_str  = f"S{season:02d}" if season > 1 else ""
    query_batch = f"{title} {season_str} batch".strip()
    query_indiv = f"{title} {season_str}".strip()

    def has_wrong_season(r_title: str) -> bool:
        detected = extract_season(r_title)
        return detected is not None and detected != season

    batches = _parse_feed(NYAA_SEARCH.format(query=requests.utils.quote(query_batch)))
    batch_results = [
        r for r in batches
        if re.search(r'\d+\s*[-~]\s*\d+|batch|complete', r["title"], re.IGNORECASE)
        and not has_wrong_season(r["title"])
    ]

    ep_map = {}
    for page in range(1, 6):
        url     = NYAA_SEARCH_PAGE.format(query=requests.utils.quote(query_indiv), page=page)
        results = _parse_feed(url)
        if not results:
            break
        new_found = 0
        for r in _filter_by_resolution(results):
            if has_wrong_season(r["title"]):
                continue
            ep = extract_episode_number(r["title"])
            if ep is None:
                continue
            cur = ep_map.get(ep)
            if cur is None or release_sort_key(r) > release_sort_key(cur):
                ep_map[ep] = r
                new_found += 1
        log.info(f"Full season search page {page}: {len(results)} results, {new_found} new episodes")
        if len(results) < 75:
            break

    if not ep_map and season > 1:
        log.info(f"No results for '{query_indiv}', falling back to plain title")
        for r in _parse_feed(NYAA_SEARCH.format(query=requests.utils.quote(title))):
            if has_wrong_season(r["title"]):
                continue
            ep = extract_episode_number(r["title"])
            if ep and (ep not in ep_map or r["seeders"] > ep_map[ep]["seeders"]):
                ep_map[ep] = r

    log.info(f"Full season search '{title}' S{season}: {len(batch_results)} batches, {len(ep_map)} unique episodes")
    return batch_results, sorted(ep_map.values(), key=lambda x: x.get("ep_num", 0))
