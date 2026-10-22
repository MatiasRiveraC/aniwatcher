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


def find_series_for_file(filename: str, watchlist: list):
    fname_lower = filename.lower()
    best, best_score = None, 0
    for entry in watchlist:
        candidate_titles = set(filter(None, [
            entry["title"],
            entry.get("title_english", ""),
            entry.get("title_romaji", ""),
        ]))
        score = 0
        for t in candidate_titles:
            words = [w for w in re.split(r'\W+', t.lower()) if len(w) > 2]
            s = sum(1 for w in words if w in fname_lower)
            score = max(score, s)
        if score > best_score:
            best_score = score
            best = entry
    if best and best_score > 0:
        log.info(f"Matched '{filename}' → '{best['title']}' (score {best_score})")
        return best["title"], best.get("season", 1)
    return None, 1


def watch_completed_folder():
    log.info("Folder watcher started")
    while True:
        settings     = get_settings()
        TORRENT_DONE = settings.get("torrent_done", "/downloads/completed")
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
                        if src in data.get("renamed", []):
                            continue

                        parent_folder = os.path.basename(root) if root != TORRENT_DONE else ""
                        # Detect "Season N" / "S01" intermediate folder
                        season_from_folder = _season_from_folder(parent_folder) if parent_folder else None
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
                            log.info(f"Already exists at dest, skipping: {new_fname}")
                            data["renamed"].append(src)
                            changed = True
                            if root != TORRENT_DONE:
                                if season_from_folder is not None:
                                    gp = os.path.dirname(root)
                                    dirs_to_clean.add(gp if gp != TORRENT_DONE else root)
                                else:
                                    dirs_to_clean.add(root)
                            continue

                        try:
                            if os.path.exists(dest):
                                log.info(f"Dest exists, removing src: {fname}")
                                os.remove(src)
                            else:
                                shutil.copy2(src, dest)
                                log.info(f"Copied+renamed: {fname} → {new_fname}")
                                if settings.get("auto_clean_metadata", True):
                                    strip_mkv_title(dest)
                                # Explicitly remove source after successful copy
                                os.remove(src)
                                log.info(f"Removed source: {src}")
                            data["renamed"].append(src)
                            changed = True
                            if root != TORRENT_DONE:
                                # If we're inside a Season N subfolder, clean the parent
                                # torrent dir (grandparent) rather than just the season subdir
                                if season_from_folder is not None:
                                    gp = os.path.dirname(root)
                                    if gp != TORRENT_DONE:
                                        dirs_to_clean.add(gp)
                                    else:
                                        dirs_to_clean.add(root)
                                else:
                                    dirs_to_clean.add(root)
                        except Exception as e:
                            log.error(f"Move failed {src}: {e}")

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
        time.sleep(settings.get("watch_interval", 60))
