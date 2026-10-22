"""
Metadata cleaning utilities.

Jellyfin reads the embedded `title` tag from MKV containers and uses it as the
episode title, overriding the filename. Release groups (e.g. ToonsHub, SubsPlease)
set this to their own name, causing every episode to show up as "ToonsHub" etc.

`strip_mkv_title` uses mkvpropedit (mkvtoolnix) to erase:
  - the segment title stored in the MKV header  (--edit info --delete title)
  - all global/track tags                        (--tags all:)

The operation is done **in-place** — no re-encode, near-instant.
"""

import logging
import os
import shutil
import subprocess

log = logging.getLogger(__name__)

_MKVPROPEDIT = shutil.which("mkvpropedit")


def mkvpropedit_available() -> bool:
    return _MKVPROPEDIT is not None


def _get_track_count(filepath: str) -> int:
    """Use mkvmerge -J to count how many tracks the file has."""
    mkvmerge = shutil.which("mkvmerge")
    if not mkvmerge:
        return 8  # safe fallback — mkvpropedit ignores non-existent tracks
    try:
        import json
        result = subprocess.run(
            [mkvmerge, "-J", filepath],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            return len(info.get("tracks", []))
    except Exception:
        pass
    return 8


def strip_mkv_title(filepath: str) -> bool:
    """
    Remove ALL name/title metadata from an MKV file in-place:
      - Segment info title       (--edit info --delete title)
      - Global tag blocks        (--tags all:)
      - Every track's Name field (--edit track:N --delete name)

    The track Name field (e.g. "ToonsHub" on the video track) is what Jellyfin
    reads as the episode title when it's present, so it must be cleared too.

    Returns True on success, False if the tool is unavailable or the command fails.
    Silently skips non-.mkv files (returns True so callers don't treat it as error).
    """
    if not filepath.lower().endswith(".mkv"):
        return True  # nothing to do for non-MKV

    if not _MKVPROPEDIT:
        log.warning("mkvpropedit not found — install mkvtoolnix to enable metadata cleaning")
        return False

    if not os.path.isfile(filepath):
        log.warning(f"strip_mkv_title: file not found: {filepath}")
        return False

    track_count = _get_track_count(filepath)

    # Build the command: segment title + global tags + every track's Name
    cmd = [
        _MKVPROPEDIT, filepath,
        "--edit", "info",
        "--delete", "title",   # segment title
        "--tags", "all:",      # all global/chapter tag blocks
    ]
    for i in range(1, track_count + 1):
        cmd += ["--edit", f"track:{i}", "--delete", "name"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            log.info(f"Cleaned metadata: {os.path.basename(filepath)}")
            return True
        else:
            log.error(f"mkvpropedit failed ({result.returncode}) for {filepath}: {result.stderr.strip()}")
            return False
    except subprocess.TimeoutExpired:
        log.error(f"mkvpropedit timed out on {filepath}")
        return False
    except Exception as e:
        log.error(f"strip_mkv_title error on {filepath}: {e}")
        return False


def inspect_file(filepath: str) -> dict:
    """
    Return embedded title metadata for a single MKV using mkvmerge -J.
    Result: {filename, path, segment_title, track_names, is_dirty}
    """
    import json as _json
    result = {"filename": os.path.basename(filepath), "path": filepath,
              "segment_title": None, "track_names": [], "is_dirty": False}

    mkvmerge = shutil.which("mkvmerge")
    if not mkvmerge or not os.path.isfile(filepath):
        return result

    try:
        r = subprocess.run([mkvmerge, "-J", filepath],
                          capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return result
        info = _json.loads(r.stdout)

        seg_title = (info.get("container", {})
                         .get("properties", {})
                         .get("title", "") or "")
        result["segment_title"] = seg_title or None

        track_names = []
        for t in info.get("tracks", []):
            name = (t.get("properties", {}).get("track_name", "") or "")
            track_names.append({
                "id":   t.get("id"),
                "type": t.get("type", ""),
                "name": name or None,
            })
        result["track_names"] = track_names
        result["is_dirty"] = bool(seg_title) or any(t["name"] for t in track_names)
    except Exception as e:
        log.warning(f"inspect_file error on {filepath}: {e}")

    return result


def inspect_series(anime_base: str, title: str, season: int) -> dict:
    """
    Find all MKV files for a series/season and return their metadata.
    Returns {path_found, files: [...]} sorted by filename.
    """
    import re as _re

    season_dir = None
    clean = _re.sub(r'[<>:"/\\|?*]', '', title).strip()
    candidate = os.path.join(anime_base, clean, f"Season {season}")
    if os.path.isdir(candidate):
        season_dir = candidate
    elif os.path.isdir(anime_base):
        clean_lower = clean.lower()
        words = [w for w in _re.split(r'\W+', clean_lower) if len(w) > 3]
        for d in os.listdir(anime_base):
            d_lower = d.lower()
            if sum(1 for w in words if w in d_lower) >= max(1, len(words) // 2):
                sp = os.path.join(anime_base, d, f"Season {season}")
                if os.path.isdir(sp):
                    season_dir = sp
                    break

    if not season_dir:
        return {"path_found": None, "files": []}

    files = []
    for fname in sorted(os.listdir(season_dir)):
        if fname.lower().endswith(".mkv"):
            files.append(inspect_file(os.path.join(season_dir, fname)))

    return {"path_found": season_dir, "files": files}


def clean_library(anime_base: str) -> dict:
    """
    Walk the entire anime library and strip title tags from every MKV found.
    Returns a summary dict: {cleaned, skipped, failed, total}.
    """
    stats = {"cleaned": 0, "skipped": 0, "failed": 0, "total": 0}

    if not os.path.isdir(anime_base):
        log.warning(f"clean_library: directory not found: {anime_base}")
        return stats

    for root, _, files in os.walk(anime_base):
        for fname in files:
            if not fname.lower().endswith(".mkv"):
                continue
            stats["total"] += 1
            path = os.path.join(root, fname)
            ok = strip_mkv_title(path)
            if ok:
                stats["cleaned"] += 1
            else:
                stats["failed"] += 1

    log.info(f"Metadata clean complete: {stats}")
    return stats
