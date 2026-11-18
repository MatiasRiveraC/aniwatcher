"""Library paths and on-disk episode checks, shared by every torrent client."""

import os
import re
import logging

log = logging.getLogger(__name__)


def _s():
    from data import get_settings
    return get_settings()


def build_save_path(series_name: str, season: int) -> str:
    anime_base = _s().get("anime_base", "/media/anime")
    clean = re.sub(r'[<>:"/\\|?*]', '', series_name).strip()
    return os.path.join(anime_base, clean, f"Season {season}")


def episode_exists_on_disk(series_name: str, season: int, episode: int) -> bool:
    """Check if an episode already exists on disk for a specific series."""
    if episode is None:
        return False

    s                = _s()
    ANIME_BASE       = s.get("anime_base",   "/media/anime")
    TORRENT_DONE     = s.get("torrent_done", "/downloads/completed")
    TORRENT_INCOMING = s.get("torrent_incoming", "")

    pattern = re.compile(rf'S{season:02d}E{episode:02d}', re.IGNORECASE)
    series_dirs = []

    expected = build_save_path(series_name, season)
    series_dirs.append(expected)

    if os.path.isdir(ANIME_BASE):
        clean = re.sub(r'[<>:"/\\|?*]', '', series_name).strip().lower()
        for d in os.listdir(ANIME_BASE):
            d_lower = d.lower()
            words = [w for w in re.split(r'\W+', clean) if len(w) > 3]
            if sum(1 for w in words if w in d_lower) >= 2:
                season_path = os.path.join(ANIME_BASE, d, f"Season {season}")
                if os.path.isdir(season_path):
                    series_dirs.append(season_path)

    # Download folders hold release names, so a match there also needs the title.
    staging = [TORRENT_DONE]
    dl_dir = os.path.join(os.path.dirname(TORRENT_DONE), "downloading")
    if os.path.isdir(dl_dir):
        staging.append(dl_dir)
    if TORRENT_INCOMING and os.path.isdir(TORRENT_INCOMING):
        staging.append(TORRENT_INCOMING)
    series_dirs.extend(staging)

    seen = set()
    for d in series_dirs:
        if not d or d in seen or not os.path.isdir(d):
            continue
        seen.add(d)
        for root, _, files in os.walk(d):
            for fname in files:
                if pattern.search(fname):
                    if d in staging:
                        fname_lower = fname.lower()
                        words = [w for w in re.split(r'\W+', series_name.lower()) if len(w) > 3]
                        if sum(1 for w in words if w in fname_lower) < 2:
                            continue
                    log.info(f"Ep S{season:02d}E{episode:02d} already on disk: {fname}")
                    return True
    return False


def inside(path: str, base: str) -> str | None:
    """
    realpath of `path` if it lies strictly inside `base`, else None.

    A plain startswith() would accept "/media/anime-old" for "/media/anime",
    and the base itself — which for TORRENT_DONE meant one delete request
    could remove the whole folder.
    """
    if not path or not base:
        return None
    real = os.path.realpath(path)
    root = os.path.realpath(base)
    try:
        if os.path.commonpath([real, root]) != root or real == root:
            return None
    except ValueError:  # different drives on Windows
        return None
    return real
