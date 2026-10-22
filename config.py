import os

DELUGE_HOST    = os.getenv("DELUGE_HOST", "localhost")
DELUGE_PORT    = int(os.getenv("DELUGE_PORT", "58846"))
DELUGE_USER    = os.getenv("DELUGE_USER", "localclient")
DELUGE_PASS    = os.getenv("DELUGE_PASS", "")
ANIME_BASE     = os.getenv("ANIME_BASE",   "/media/anime")
TORRENT_DONE   = os.getenv("TORRENT_DONE", "/downloads/completed")
POLL_INTERVAL  = int(os.getenv("POLL_INTERVAL", "900"))
WATCH_INTERVAL = int(os.getenv("WATCH_INTERVAL", "60"))
DATA_FILE      = "/data/watchlist.json"

MAL_API       = "https://api.myanimelist.net/v2"
MAL_CLIENT_ID = os.getenv("MAL_CLIENT_ID", "")

NYAA_RSS         = "https://nyaa.si/?page=rss&c=1_2&f=0&q={query}"
NYAA_SEARCH      = "https://nyaa.si/?page=rss&c=1_2&f=0&q={query}&s=seeders&o=desc"
NYAA_SEARCH_PAGE = "https://nyaa.si/?page=rss&c=1_2&f=0&q={query}&s=seeders&o=desc&p={page}"

VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv"}
