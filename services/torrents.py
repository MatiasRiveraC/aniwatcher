"""Send a torrent to whichever client is configured (`torrent_client` setting)."""

import logging

log = logging.getLogger(__name__)

CLIENT_NAMES = {"deluge": "Deluge", "qbittorrent": "qBittorrent"}


def client_name() -> str:
    from data import get_settings
    return CLIENT_NAMES.get(get_settings().get("torrent_client", "deluge"), "Deluge")


def add_torrent(magnet_or_url: str) -> bool:
    from data import get_settings
    client = get_settings().get("torrent_client", "deluge")
    if client == "qbittorrent":
        from services.qbittorrent import add_torrent_to_qbittorrent
        return add_torrent_to_qbittorrent(magnet_or_url)
    if client != "deluge":
        log.warning(f"Unknown torrent_client {client!r}, using Deluge")
    from services.deluge import add_torrent_to_deluge
    return add_torrent_to_deluge(magnet_or_url)
