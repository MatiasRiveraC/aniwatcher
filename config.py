import os

def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


# Which client torrents are sent to: "deluge" or "qbittorrent".
TORRENT_CLIENT = os.getenv("TORRENT_CLIENT", "deluge").strip().lower()

DELUGE_HOST    = os.getenv("DELUGE_HOST", "localhost")
DELUGE_PORT    = int(os.getenv("DELUGE_PORT", "58846"))
DELUGE_USER    = os.getenv("DELUGE_USER", "localclient")
DELUGE_PASS    = os.getenv("DELUGE_PASS", "")

# qBittorrent Web UI. Torrents are added under QBIT_CATEGORY and saved to
# TORRENT_INCOMING; once finished, their files are handed to TORRENT_DONE,
# where the renamer picks them up — the hand-off Deluge's "move completed"
# gives. How depends on QBIT_STOP_SEEDING:
#   false (default) – the torrent keeps seeding; its files are hard-linked
#                     into TORRENT_DONE (copied if that is not possible).
#   true            – the torrent is removed from qBittorrent, keeping the
#                     files, and they are moved into TORRENT_DONE.
QBIT_URL           = os.getenv("QBIT_URL", "http://localhost:8080")
QBIT_USER          = os.getenv("QBIT_USER", "admin")
QBIT_PASS          = os.getenv("QBIT_PASS", "")
QBIT_CATEGORY      = os.getenv("QBIT_CATEGORY", "aniwatcher")
QBIT_STOP_SEEDING  = _bool("QBIT_STOP_SEEDING")

ANIME_BASE       = os.getenv("ANIME_BASE",   "/media/anime")
TORRENT_DONE     = os.getenv("TORRENT_DONE", "/downloads/completed")
TORRENT_INCOMING = os.getenv("TORRENT_INCOMING", "/downloads/incoming")

# When true, the folder settings come from the environment only and cannot be
# changed from the web UI. The UI has no login, and it can delete files inside
# TORRENT_DONE — pointing that at the library from a browser would wipe it.
LOCK_PATHS     = _bool("LOCK_PATHS")
POLL_INTERVAL  = int(os.getenv("POLL_INTERVAL", "900"))
WATCH_INTERVAL = int(os.getenv("WATCH_INTERVAL", "60"))
# MB/s cap for copying finished files into the library (0 = no cap). Only used when
# a move cannot be a rename (another disk, or another mount).
COPY_LIMIT_MBPS = int(os.getenv("COPY_LIMIT_MBPS", "0"))
DATA_FILE      = "/data/watchlist.json"

MAL_API       = "https://api.myanimelist.net/v2"
MAL_CLIENT_ID = os.getenv("MAL_CLIENT_ID", "")

NYAA_RSS         = "https://nyaa.si/?page=rss&c=1_2&f=0&q={query}"
NYAA_SEARCH      = "https://nyaa.si/?page=rss&c=1_2&f=0&q={query}&s=seeders&o=desc"
NYAA_SEARCH_PAGE = "https://nyaa.si/?page=rss&c=1_2&f=0&q={query}&s=seeders&o=desc&p={page}"

VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv"}
