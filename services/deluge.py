import os
import re
import logging

from deluge_client import DelugeRPCClient

log = logging.getLogger(__name__)


def _s():
    from data import get_settings
    return get_settings()


def add_torrent_to_deluge(magnet_or_url: str) -> bool:
    s = _s()
    try:
        client = DelugeRPCClient(
            s["deluge_host"], int(s["deluge_port"]),
            s["deluge_user"], s["deluge_pass"],
        )
        client.connect()
        options = {}
        if magnet_or_url.startswith("magnet:"):
            client.call("core.add_torrent_magnet", magnet_or_url, options)
        else:
            client.call("core.add_torrent_url", magnet_or_url, options)
        client.disconnect()
        log.info("Added torrent to Deluge")
        return True
    except Exception as e:
        log.error(f"Deluge error: {e}")
        return False


def build_save_path(series_name: str, season: int) -> str:
    anime_base = _s().get("anime_base", "/media/anime")
    clean = re.sub(r'[<>:"/\\|?*]', '', series_name).strip()
    return os.path.join(anime_base, clean, f"Season {season}")


def episode_exists_on_disk(series_name: str, season: int, episode: int) -> bool:
    """Check if an episode already exists on disk for a specific series."""
    if episode is None:
        return False

    s            = _s()
    ANIME_BASE   = s.get("anime_base",   "/media/anime")
    TORRENT_DONE = s.get("torrent_done", "/downloads/completed")

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

    series_dirs.append(TORRENT_DONE)
    dl_dir = os.path.join(os.path.dirname(TORRENT_DONE), "downloading")
    if os.path.isdir(dl_dir):
        series_dirs.append(dl_dir)

    seen = set()
    for d in series_dirs:
        if not d or d in seen or not os.path.isdir(d):
            continue
        seen.add(d)
        for root, _, files in os.walk(d):
            for fname in files:
                if pattern.search(fname):
                    if d in (TORRENT_DONE, dl_dir):
                        fname_lower = fname.lower()
                        words = [w for w in re.split(r'\W+', series_name.lower()) if len(w) > 3]
                        if sum(1 for w in words if w in fname_lower) < 2:
                            continue
                    log.info(f"Ep S{season:02d}E{episode:02d} already on disk: {fname}")
                    return True
    return False
