import os
import json
import logging

from config import DATA_FILE, DELUGE_HOST, DELUGE_PORT, DELUGE_USER, DELUGE_PASS, \
    ANIME_BASE, TORRENT_DONE, POLL_INTERVAL, WATCH_INTERVAL, MAL_CLIENT_ID, \
    TORRENT_CLIENT, QBIT_URL, QBIT_USER, QBIT_PASS, QBIT_CATEGORY, QBIT_STOP_SEEDING, \
    TORRENT_INCOMING, LOCK_PATHS

log = logging.getLogger(__name__)

EMPTY_DATA = {"watchlist": [], "downloaded": [], "renamed": [], "notifications": [], "settings": {}}

DEFAULT_SETTINGS = {
    "preferred_resolution": "1080",
    "preferred_groups":     "SubsPlease,Erai-raws,NC-Raws,EMBER",
    "poll_interval":        POLL_INTERVAL,
    "watch_interval":       WATCH_INTERVAL,
    "anime_base":           ANIME_BASE,
    "torrent_done":         TORRENT_DONE,
    "torrent_incoming":     TORRENT_INCOMING,
    "torrent_client":       TORRENT_CLIENT,
    "deluge_host":          DELUGE_HOST,
    "deluge_port":          DELUGE_PORT,
    "deluge_user":          DELUGE_USER,
    "deluge_pass":          DELUGE_PASS,
    "qbit_url":             QBIT_URL,
    "qbit_user":            QBIT_USER,
    "qbit_pass":            QBIT_PASS,
    "qbit_category":        QBIT_CATEGORY,
    "qbit_stop_seeding":    QBIT_STOP_SEEDING,
    "mal_client_id":        MAL_CLIENT_ID,
    "auto_clean_metadata":  True,
}

# Folder settings that LOCK_PATHS pins to the environment.
PATH_KEYS = ("anime_base", "torrent_done", "torrent_incoming")

# Never sent back to the browser: the UI has no login, so anyone on the
# network could read them. A blank value on save means "keep the current one".
SECRET_KEYS = ("deluge_pass", "qbit_pass")


def locked_keys() -> tuple:
    return PATH_KEYS if LOCK_PATHS else ()


def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE) as f:
                data = json.load(f)
            for key in EMPTY_DATA:
                data.setdefault(key, [] if key != "settings" else {})
            return data
        except (json.JSONDecodeError, ValueError) as e:
            log.error(f"Corrupted watchlist.json ({e}), resetting to empty")
            save_data(EMPTY_DATA.copy())
            return EMPTY_DATA.copy()
    return EMPTY_DATA.copy()


def save_data(data: dict) -> None:
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_settings() -> dict:
    """Return merged settings: defaults overridden by any saved values."""
    data = load_data()
    s = DEFAULT_SETTINGS.copy()
    s.update(data.get("settings", {}))
    for key in locked_keys():
        s[key] = DEFAULT_SETTINGS[key]
    return s


def save_settings(settings: dict) -> None:
    """Persist only known settings keys, never locked ones."""
    data = load_data()
    data["settings"] = {k: settings[k] for k in DEFAULT_SETTINGS
                        if k in settings and k not in locked_keys()}
    save_data(data)
