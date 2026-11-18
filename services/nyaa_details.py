"""
What a nyaa release page says beyond its title: the uploader's description
(markdown: screenshots, MediaInfo, notes), the files inside the torrent and
the comments. Read from https://nyaa.si/view/<id> for the release picker.
"""

import logging
import re
import time
from html.parser import HTMLParser

import requests

from utils.parsing import episode_marker

log = logging.getLogger(__name__)

VIEW_URL  = "https://nyaa.si/view/{id}"
CACHE_TTL = 600
_cache: dict = {}

# Files a season pack carries besides its episodes.
EXTRA_RE = re.compile(
    r'\b(?:NC ?OP|NC ?ED|OP\d*|ED\d*|Opening|Ending|Creditless|Preview|Menu|PV\d*|CM\d*|'
    r'Trailer|Teaser|Bonus|Extras?|Making|Interview|Commentary|SP\d*|Specials?|OVA|OAD)\b', re.I)
VIDEO_RE = re.compile(r'\.(mkv|mp4|avi|m2ts|ts|webm|wmv|ogm)$', re.I)


class _PageParser(HTMLParser):
    """Collects the description, the (nested) file list and the comments."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.description = ""
        self.files = []          # {"path", "size"}
        self.comments = []       # {"user", "text"}
        self.info = {}
        self._in = None          # what the text being read belongs to
        self._buf = []
        self._folders = []       # folder names, one per open folder <ul>
        self._ul_depth = 0       # <ul> depth inside the file list
        self._folder_uls = []    # depths at which a folder's <ul> opened
        self._in_list = False
        self._pending_folder = None
        self._file_name = None
        self._comment_user = None
        self._label = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "div" and a.get("id") == "torrent-description":
            self._start("description")
        elif tag == "div" and "torrent-file-list" in cls:
            self._in_list = True
        elif tag == "div" and "comment-content" in cls:
            self._start("comment")
        elif tag == "a" and "/user/" in (a.get("href") or "") and self._in is None:
            self._start("user")
        elif self._in_list:
            if tag == "ul":
                self._ul_depth += 1
                if self._pending_folder is not None:
                    self._folders.append(self._pending_folder)
                    self._folder_uls.append(self._ul_depth)
                    self._pending_folder = None
            elif tag == "a" and "folder" in cls:
                self._start("folder")
            elif tag == "li":
                self._start("file")
            elif tag == "span" and "file-size" in cls and self._in == "file":
                self._file_name = "".join(self._buf).strip()
                self._start("size")
        elif tag == "div" and "col-md-1" in cls:
            self._start("label")

    def handle_endtag(self, tag):
        if self._in == "description" and tag == "div":
            self.description = self._take()
        elif self._in == "comment" and tag == "div":
            self.comments.append({"user": self._comment_user or "", "text": self._take()})
            self._comment_user = None
        elif self._in == "user" and tag == "a":
            name = self._take()
            if self._label == "Submitter":
                self.info["submitter"] = name
                self._label = None
            else:
                self._comment_user = name
        elif self._in == "label" and tag == "div":
            self._label = self._take().rstrip(":")
        elif self._in == "folder" and tag == "a":
            self._pending_folder = self._take()
        elif self._in == "size" and tag == "span":
            size = self._take().strip("() ")
            self.files.append({"path": "/".join(self._folders + [self._file_name]), "size": size})
            self._file_name = None
        elif self._in == "file" and tag == "li":
            name = self._take()                 # a file with no size span
            if name:
                self.files.append({"path": "/".join(self._folders + [name]), "size": ""})
        elif self._in_list and tag == "ul":
            if self._folder_uls and self._folder_uls[-1] == self._ul_depth:
                self._folder_uls.pop()
                self._folders.pop()
            self._ul_depth -= 1
        elif self._in_list and tag == "div" and self._ul_depth == 0:
            self._in_list = False

    def handle_data(self, data):
        if self._in:
            self._buf.append(data)
        elif self._label in ("Information", "Submitter") and data.strip():
            self.info[self._label.lower()] = data.strip()
            self._label = None
        elif self._label and data.strip():
            self._label = None

    def _start(self, what):
        self._in = what
        self._buf = []

    def _take(self) -> str:
        text = "".join(self._buf).strip()
        self._in = None
        self._buf = []
        return text


def _size_mb(size: str) -> float:
    m = re.match(r'([\d.]+)\s*(KiB|MiB|GiB|TiB|B)', size or "")
    if not m:
        return 0.0
    return float(m.group(1)) * {"B": 1 / 2**20, "KiB": 1 / 1024, "MiB": 1, "GiB": 1024, "TiB": 2**20}[m.group(2)]


def release_details(view_id: int) -> dict:
    """Description, files and comments of one nyaa release (cached 10 min)."""
    hit = _cache.get(view_id)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]

    resp = requests.get(VIEW_URL.format(id=view_id), timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    page = _PageParser()
    page.feed(resp.text)

    info_url = page.info.get("information")
    if not (info_url or "").startswith(("http://", "https://")):
        info_url = None

    files = []
    for f in page.files:
        name = f["path"].rsplit("/", 1)[-1]
        video = bool(VIDEO_RE.search(name))
        extra = video and bool(EXTRA_RE.search(re.sub(r'\[[^\]]*\]|\([^)]*\)', ' ', name)))
        files.append({
            **f,
            "video": video,
            "extra": extra,
            "episode": episode_marker(name) if video and not extra else None,
        })
    episodes = sorted({f["episode"] for f in files if f["episode"] is not None})

    out = {
        "id":          view_id,
        "url":         VIEW_URL.format(id=view_id),
        "description": page.description,
        "files":       files,
        "episodes":    episodes,
        "extras":      sum(f["extra"] for f in files),
        "other_files": sum(not f["video"] for f in files),
        "largest_mb":  round(max((_size_mb(f["size"]) for f in files), default=0)),
        "comments":    page.comments[:20],
        "comment_count": len(page.comments),
        "submitter":   page.info.get("submitter"),
        "info_url":    info_url,
    }
    _cache[view_id] = (time.time(), out)
    if len(_cache) > 200:
        for k, _ in sorted(_cache.items(), key=lambda kv: kv[1][0])[:50]:
            _cache.pop(k, None)
    return out
