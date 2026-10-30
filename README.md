# AniWatcher

A self-hosted anime downloader for your home server.
AniWatcher watches nyaa.si for new episodes of the shows on your watchlist, sends them to Deluge or qBittorrent, and then renames and sorts the finished files into a Jellyfin/Plex-friendly library.

## Features

- **Watchlist**: search MyAnimeList, add a show and season, and AniWatcher tracks new episodes automatically.
- **Automatic polling**: checks the nyaa.si RSS feed on a schedule (default every 15 min) and picks the best-seeded release that matches your preferred resolution and release groups.
- **Deluge or qBittorrent**: pushes torrents to a Deluge daemon over RPC, or to qBittorrent over its Web UI API.
- **Auto rename & organize**: moves finished video files into `Show/Season N/Show - SxxEyy.ext`.
- **Metadata cleaning**: removes the release-group `title` tags that MKV files carry, which Jellyfin would otherwise show as the episode name (uses `mkvpropedit`).
- **Manual tools**: full-season grabs, picking a release by hand, a disk rescan, a library browser, an MKV metadata inspector, and a view of the completed folder.
- **Web UI**: a single-page dashboard with live logs, download history, notifications, and settings you can change at runtime.

## How it works

1. Add an anime and season in the web UI.
2. Every `POLL_INTERVAL` seconds, AniWatcher queries nyaa.si and chooses the best matching release.
3. The torrent goes to Deluge or qBittorrent.
4. Every `WATCH_INTERVAL` seconds, a folder watcher scans the completed folder. (With qBittorrent, finished torrents are first removed from qBittorrent — keeping the files — and moved there; see [Using qBittorrent](#using-qbittorrent).)
5. New video files are renamed and moved, for example:

   `[SubsPlease] Frieren - 28 (1080p).mkv` → `Frieren - S01E28.mkv`

```
<ANIME_BASE>/
  Frieren Beyond Journey's End/
    Season 1/
      Frieren Beyond Journey's End - S01E01.mkv
      Frieren Beyond Journey's End - S01E02.mkv
  Solo Leveling/
    Season 2/
      Solo Leveling - S02E01.mkv
```

## Requirements

- Docker + Docker Compose (recommended), **or** Python 3.12+ with `mkvtoolnix` installed
- A running [Deluge](https://deluge-torrent.org/) daemon with remote connections enabled, **or** [qBittorrent](https://www.qbittorrent.org/) with the Web UI on
- A MyAnimeList API client ID (free)
- The torrent client and AniWatcher must both be able to reach the download folders and the anime library folder

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/<your-user>/aniwatcher.git
cd aniwatcher
```

### 2. Enable remote access on the Deluge daemon

In Deluge go to **Preferences → Daemon**:

- Turn on **Allow Remote Connections**
- Note the daemon port (default `58846`)

Add a user for AniWatcher to Deluge's `auth` file (in the Deluge config directory). Each line has the form `username:password:level`; `10` is the admin level:

```
aniwatcher:choose_a_strong_password:10
```

Restart Deluge after you edit the file.

### Using qBittorrent

Set `TORRENT_CLIENT=qbittorrent` and the `QBIT_*` variables (or pick qBittorrent on the Settings tab). The Web UI must be enabled; the user and password are the Web UI login.

- Torrents are added under the `QBIT_CATEGORY` category (created if missing) and saved to `TORRENT_INCOMING`.
- When one finishes, its files are handed to `TORRENT_DONE` and the renamer handles them exactly as with Deluge. How, depends on `QBIT_STOP_SEEDING` (also a checkbox on the Settings tab):
  - `false` (default) — **keeps seeding.** The files are hard-linked into `TORRENT_DONE` (a second name for the same data, so no extra space; copied if a hard link is impossible), and the renamer copies them on into the library before cleaning titles, so the seeding files are never modified. The library copy does take its own space while the torrent seeds. The torrent is tagged `aniwatcher-imported` so it is handed over once.
  - `true` — **stops seeding.** The torrent is removed from qBittorrent, keeping the files, and they are moved into `TORRENT_DONE`. Removing it first stops qBittorrent seeding from a path that is about to disappear.
- qBittorrent reports paths as **it** sees them, so both containers must see the downloads at the **same path** — e.g. mount the host's downloads folder at `/downloads` in both, with `TORRENT_INCOMING=/downloads/aniwatcher/incoming` and `TORRENT_DONE=/downloads/aniwatcher/done`. Keeping both under one mount also makes the move an instant rename instead of a copy.
- With `QBIT_STOP_SEEDING=true`, anything left in `TORRENT_INCOMING` that no torrent accounts for (a move that failed) is retried after 10 minutes.

### 3. Get a MyAnimeList client ID

1. Sign in at <https://myanimelist.net/apiconfig> and click **Create ID**.
2. Set the app type to *web* and fill in the required fields (any placeholder URL works).
3. Copy the **Client ID**.

### 4. Configure your environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your own values (see [Configuration](#configuration)).
`.env` is listed in `.gitignore`, so your credentials never get committed.

### 5. Deploy with Docker Compose

```bash
docker compose up -d --build
```

Then open `http://<your-server>:5000`.

`docker-compose.yml` bind-mounts `ANIME_BASE` and `TORRENT_DONE` from the host at the **same path** inside the container, so the paths Deluge reports match the paths AniWatcher sees. The container runs as UID/GID `568`. Make sure that user can read and write both folders, or change `user:` in the compose file and the IDs in the `Dockerfile`.

### Alternative: run without Docker

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# install mkvtoolnix with your package manager, e.g. apt install mkvtoolnix
set -a; source .env; set +a      # load the variables into the shell
python app.py
```

Note: app state is stored in `/data/watchlist.json`, so the `/data` directory must exist and be writable (or change `DATA_FILE` in `config.py`).

## Configuration

These values come from environment variables (`.env`). Most of them can also be changed later on the **Settings** tab. Values saved there are kept in `/data/watchlist.json` and take priority over the environment.

| Variable         | Default                | Description                                   |
|------------------|------------------------|-----------------------------------------------|
| `TORRENT_CLIENT` | `deluge`               | `deluge` or `qbittorrent`                     |
| `DELUGE_HOST`    | `localhost`            | Deluge daemon host/IP                         |
| `DELUGE_PORT`    | `58846`                | Deluge daemon RPC port                        |
| `DELUGE_USER`    | `localclient`          | Deluge auth user                              |
| `DELUGE_PASS`    | *(empty)*              | Deluge auth password                          |
| `QBIT_URL`       | `http://localhost:8080`| qBittorrent Web UI address                    |
| `QBIT_USER`      | `admin`                | qBittorrent Web UI user                       |
| `QBIT_PASS`      | *(empty)*              | qBittorrent Web UI password                   |
| `QBIT_CATEGORY`  | `aniwatcher`           | Category AniWatcher's torrents are added under |
| `QBIT_STOP_SEEDING` | `false`             | `true` = remove finished torrents from qBittorrent and move the files |
| `MAL_CLIENT_ID`  | *(empty)*              | MyAnimeList API client ID                     |
| `ANIME_BASE`     | `/media/anime`         | Root folder of the anime library              |
| `TORRENT_DONE`   | `/downloads/completed` | Deluge's completed-downloads folder           |
| `TORRENT_INCOMING` | `/downloads/incoming` | qBittorrent only: where torrents download    |
| `LOCK_PATHS`     | `false`                | `true` = folder paths can't be changed from the UI |
| `PUID` / `PGID`  | `568`                  | User/group the container runs as (Docker Compose) |
| `POLL_INTERVAL`  | `900`                  | Seconds between nyaa.si polls                 |
| `WATCH_INTERVAL` | `60`                   | Seconds between completed-folder scans        |
| `WEB_PORT`       | `5000`                 | Host port for the web UI (Docker Compose only) |

## Project structure

```
app.py              Flask app factory + background threads
config.py           Environment-based configuration
data.py             JSON persistence + settings merge
routes/             HTTP + WebSocket endpoints (watchlist, downloads, settings, system…)
services/           Deluge, MAL, nyaa, poller, renamer, MKV metadata cleaner
utils/              Filename/episode parsing helpers
templates/, static/ Web UI
```

## Security notes

- The web UI has **no authentication**. Run it only on a trusted LAN or behind a reverse proxy that requires a login.
- Never commit `.env`. Use `.env.example` as the template.
- Set `LOCK_PATHS=true` on a shared network. Without it, anyone who can open the UI can change the folder settings, and the completed-folder tool can delete files there.
- Passwords are never sent back to the browser; leaving a password field blank on the Settings tab keeps the saved one.
