import logging

from deluge_client import DelugeRPCClient

# Kept importable from here for anything that still does.
from services.library import build_save_path, episode_exists_on_disk  # noqa: F401

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
