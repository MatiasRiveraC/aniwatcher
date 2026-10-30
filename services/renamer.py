import os
import re
import shutil
import logging
import time

from config import VIDEO_EXTS
from data import load_data, save_data, get_settings
from services.deluge import build_save_path
from services.metadata import strip_mkv_title

log = logging.getLogger(__name__)


def parse_episode_info(filename: str):
    stem = os.path.splitext(filename)[0]
    m = re.search(r'S(\d{1,2})E(\d{2,4})', stem, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r'(\d{1,2})x(\d{2,4})', stem, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Standalone EP#### format (e.g. One.Piece.EP1156)
    m = re.search(r'\bEP(\d{2,4})\b', stem, re.IGNORECASE)
    if m:
        return None, int(m.group(1))
    # Bare episode number after dash/space/underscore/dot
    m = re.search(r'[-\s_.](\d{2,4})(?:v\d)?(?:[-\s_.\[\(]|$)', stem)
    if m:
        return None, int(m.group(1))
    # Bare OVA/Special with no episode number → S00E01
    if re.search(r'\b(OVA|OAD|Special)\b', stem, re.IGNORECASE):
        return 0, 1
    return None, None


def _season_from_folder(folder_name: str):
    """Return season int if folder is named 'Season N' / 'S01' etc., else None."""
    m = re.search(r'\bseason\s*(\d+)\b', folder_name, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Standalone "S01" / "S1" folder (but not inside a real title)
    m = re.fullmatch(r'S(\d{1,2})', folder_name, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


# Words that say nothing about which show a file is: English/Japanese filler and season wording
_FILLER_WORDS = {"the", "an", "of", "and", "to", "in", "on", "no", "wa", "ga", "ni", "wo", "de",
                 "season", "part", "cour"}


def _words(text: str) -> list:
    return [w for w in re.split(r'[^0-9a-z]+', text.lower()) if w]


def _key_words(name: str) -> set:
    """The words of a show name that must all appear in a filename for it to match."""
    return {w for w in _words(name)
            if len(w) > 1 and w not in _FILLER_WORDS and not re.fullmatch(r'\d+(st|nd|rd|th)', w)}


def find_series_for_file(filename: str, watchlist: list):
    """Pick the watchlist entry a file belongs to. One of the entry's names (folder title,
    MAL English/romaji titles, nyaa searches) must have all its key words in the filename
    as whole words; when several entries match, the most specific name wins."""
    file_words = set(_words(filename))
    best, best_name, best_score = None, "", 0
    for entry in watchlist:
        names = [entry["title"], entry.get("title_english", ""), entry.get("title_romaji", ""),
                 entry.get("search_title", ""), *(entry.get("search_titles") or [])]
        for name in filter(None, names):
            key = _key_words(name)
            if key and key <= file_words and len(key) > best_score:
                best, best_name, best_score = entry, name, len(key)
    if best:
        log.info(f"Matched '{filename}' → '{best['title']}' (via '{best_name}')")
        return best["title"], best.get("season", 1)
    return None, 1


_remove_failed = set()  # sources whose delete error was already logged

# Shown in the web page: epoch seconds of the last finished pass and the next one
watcher_state = {"running": False, "last_run": None, "next_run": None}


def _remove_source(src: str) -> bool:
    """Delete a completed file that is already in the library. True once it's gone."""
    try:
        os.remove(src)
        log.info(f"Removed source: {src}")
    except FileNotFoundError:
        pass
    except OSError as e:
        # Log once per file; the watcher retries on every pass
        if src not in _remove_failed:
            log.error(f"In library but could not remove source {src}: {e}")
            _remove_failed.add(src)
        return False
    _remove_failed.discard(src)
    return True


def _copy_contents(src: str, dst: str):
    """Copy the file's data and, when allowed, its timestamps. Not shutil.copy2: on a
    TrueNAS dataset with an SMB/NFSv4 ACL its chmod and xattr copy fail with EPERM, and
    the file should take its permissions from the library folder's ACL anyway."""
    shutil.copyfile(src, dst)
    try:
        st = os.stat(src)
        os.utime(dst, ns=(st.st_atime_ns, st.st_mtime_ns))
    except OSError:
        pass


def _torrent_dir(root: str, top: str, season_from_folder):
    """The folder a torrent created under `top`, or None for files directly in it."""
    if root == top:
        return None
    # Inside a Season N subfolder, clean the torrent dir (grandparent) rather than the season subdir
    if season_from_folder is not None:
        gp = os.path.dirname(root)
        if gp != top:
            return gp
    return root


def watch_completed_folder():
    log.info("Folder watcher started")
    while True:
        settings     = get_settings()
        TORRENT_DONE = settings.get("torrent_done", "/downloads/completed")
        watcher_state["running"] = True
        try:
            if os.path.isdir(TORRENT_DONE):
                data, changed = load_data(), False
                dirs_to_clean = set()

                for root, dirs, files in os.walk(TORRENT_DONE):
                    for fname in files:
                        ext = os.path.splitext(fname)[1].lower()
                        if ext not in VIDEO_EXTS:
                            continue
                        src = os.path.join(root, fname)
                        parent_folder = os.path.basename(root) if root != TORRENT_DONE else ""
                        # Detect "Season N" / "S01" intermediate folder
                        season_from_folder = _season_from_folder(parent_folder) if parent_folder else None
                        torrent_dir = _torrent_dir(root, TORRENT_DONE, season_from_folder)
                        # Seen on an earlier pass but still here: its delete failed, so go
                        # through the flow again (dest exists → retry the delete)
                        already = src in data.get("renamed", [])

                        grandparent_folder = ""
                        if season_from_folder is not None and root != TORRENT_DONE:
                            gp = os.path.dirname(root)
                            grandparent_folder = os.path.basename(gp) if gp != TORRENT_DONE else ""

                        series_name, season = find_series_for_file(fname, data["watchlist"])

                        if not series_name:
                            # Try grandparent first when inside a Season N subfolder
                            if grandparent_folder:
                                series_name, season = find_series_for_file(grandparent_folder, data["watchlist"])
                                if series_name:
                                    log.info(f"Matched via grandparent folder '{grandparent_folder}' → '{series_name}'")
                            # Fall back to immediate parent (non-Season folders)
                            if not series_name and parent_folder and season_from_folder is None:
                                series_name, season = find_series_for_file(parent_folder, data["watchlist"])
                                if series_name:
                                    log.info(f"Matched via folder name '{parent_folder}' → '{series_name}'")

                        if not series_name:
                            if not already:
                                log.info(f"No watchlist match for: {fname} (folder: {parent_folder})")
                            continue

                        parsed_season, episode = parse_episode_info(fname)
                        # Priority: explicit SxxExx in filename > Season N folder > watchlist season
                        # NOTE: use `is not None` so season 0 (OVA) isn't treated as falsy
                        s = parsed_season if parsed_season is not None else (season_from_folder or season)
                        if season_from_folder and not parsed_season:
                            log.info(f"Season {season_from_folder} detected from folder '{parent_folder}'")
                        if episode is None:
                            log.warning(f"No episode number: {fname}")
                            continue

                        dest_dir     = build_save_path(series_name, s)
                        os.makedirs(dest_dir, exist_ok=True)
                        clean_series = re.sub(r'[<>:"/\\|?*]', '', series_name).strip()
                        new_fname    = f"{clean_series} - S{s:02d}E{episode:02d}{ext}"
                        dest         = os.path.join(dest_dir, new_fname)

                        if os.path.exists(dest):
                            if not already:
                                log.info(f"Already exists at dest, removing source: {new_fname}")
                        else:
                            # Copy under a temp name so a failed copy never leaves a
                            # partial file at dest that a later pass would trust
                            tmp = dest + ".part"
                            try:
                                _copy_contents(src, tmp)
                                os.replace(tmp, dest)
                            except Exception as e:
                                log.error(f"Copy failed {src}: {e}")
                                try:
                                    os.remove(tmp)
                                except OSError:
                                    pass
                                continue
                            log.info(f"Copied+renamed: {fname} → {new_fname}")
                            if settings.get("auto_clean_metadata", True):
                                strip_mkv_title(dest)

                        # The episode is in the library now: record it so a failed delete
                        # below is retried on the next pass instead of being forgotten
                        if not already:
                            data["renamed"].append(src)
                            changed = True
                        if _remove_source(src) and torrent_dir:
                            dirs_to_clean.add(torrent_dir)

                for d in dirs_to_clean:
                    try:
                        if not os.path.isdir(d):
                            continue
                        # Walk entire subtree, remove leftover non-video files
                        for sub_root, sub_dirs, sub_files in os.walk(d, topdown=False):
                            for leftover in sub_files:
                                lpath = os.path.join(sub_root, leftover)
                                ext_l = os.path.splitext(leftover)[1].lower()
                                if ext_l not in VIDEO_EXTS:
                                    os.remove(lpath)
                                    log.info(f"Removed leftover file: {leftover}")
                            # Remove subdir if now empty
                            if sub_root != d and not os.listdir(sub_root):
                                os.rmdir(sub_root)
                                log.info(f"Removed empty subdir: {sub_root}")
                        # Remove the top dir if now empty
                        if not os.listdir(d):
                            os.rmdir(d)
                            log.info(f"Removed empty dir: {d}")
                    except Exception as e:
                        log.warning(f"Could not remove dir {d}: {e}")

                if changed:
                    save_data(data)
        except Exception as e:
            log.error(f"Watcher error: {e}")
        interval = settings.get("watch_interval", 60)
        now      = time.time()
        watcher_state.update(running=False, last_run=now, next_run=now + interval)
        time.sleep(interval)
