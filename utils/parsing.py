import re
import unicodedata


def extract_episode_number(title: str):
    # Try SxxExx first
    m = re.search(r'S\d{1,2}E(\d{2,4})', title, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Try 01x16 format
    m = re.search(r'\d{1,2}x(\d{2,4})', title, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Try standalone EP#### format (e.g. One.Piece.EP1156)
    m = re.search(r'\bEP(\d{2,4})\b', title, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Fall back to bare episode number after dash/space/underscore/dot (2-4 digits)
    m = re.search(r'[-\s_.](\d{2,4})(?:v\d)?(?:[-\s_.\[\(]|$)', title)
    return int(m.group(1)) if m else None


def extract_season(title: str):
    patterns = [
        # "Season 4" / "Season4"
        r'[Ss]eason\s*(\d+)',
        # "S04E01" or "S4E1"
        r'\bS(\d{1,2})E\d+',
        # "4th Season" / "2nd Season" etc.
        r'\b(\d+)(?:st|nd|rd|th)\s+[Ss]eason',
        # Standalone "S04" (without episode number)
        r'\bS(\d{1,2})\b',
        # "Part 2" / "Part II" (numeric only)
        r'\b[Pp]art\s*(\d+)\b',
        # "Cour 2" / "2nd Cour"
        r'\b[Cc]our\s*(\d+)\b',
        r'\b(\d+)(?:st|nd|rd|th)\s+[Cc]our\b',
    ]
    for pat in patterns:
        m = re.search(pat, title)
        if m:
            return int(next(g for g in m.groups() if g is not None))
    return None


# ── Which show is a release? ──────────────────────────────────────────────────
#
# Nyaa's search is fuzzy: "Genshiken" also returns Genshiken Nidaime (a sequel)
# and Genshin Impact, "Himouto! Umaru-chan" returns Umaru-chan R (season 2).
# A release counts as the show only if its name — the title minus group tags,
# bracketed metadata, episode numbers and quality words — is one of the show's
# known names, word for word.

_QUALITY = (r'\d{3,4}p|\d{3,4}x\d{3,4}|BD(?:Rip|Remux)?|Blu-?Ray|DVD(?:Rip)?|WEB(?:-?DL|-?Rip)?|'
            r'HEVC|AVC|[xh]\.?26[45]|10-?bits?|8-?bits?|FLAC|AAC|Opus|AC3|E-?AC-?3|DTS|'
            r'Batch|Complete|Dual[\s.-]?Audio|Multi[\s.-]?(?:Audio|Subs?)')
_NAME_CUTS = [
    re.compile(r'\s[-–~|]\s*(?:S\d|E[Pp]?\s*\d|\d|Ep(?:isode)?\b|Vol)', re.I),  # " - 05", " - S2"
    re.compile(r'\s(?:E[Pp]?)?\d{1,4}\s*[-~]\s*(?:E[Pp]?)?\d{1,4}\b', re.I),     # " 01-12"
    re.compile(r'\bS\d{1,2}(?:E\d+)?\b', re.I),
    re.compile(r'\b(?:\d+(?:st|nd|rd|th)\s+)?Season\b', re.I),
    re.compile(r'\bE[Pp]?\d{1,4}\b|\bEpisode\b|\bVol(?:ume)?\.?\s*\d', re.I),
    re.compile(rf'\b(?:{_QUALITY})\b', re.I),
]
# Words that may trail a show's name without making it another show. Applied to
# both sides of the comparison, so a title that contains one still matches.
_NOISE = {
    'tv', 'series', 'the', 'ova', 'ovas', 'oad', 'oads', 'special', 'specials', 'sp', 'extras',
    'end', 'fin', 'uncensored', 'uncut', 'remastered', 'remux', 'hd', 'sd', 'eng', 'english',
    'sub', 'subs', 'subbed', 'softsubs', 'dub', 'dubbed', 'dual', 'audio', 'multi', 'jp', 'jpn',
    'v2', 'v3', 'v4', 'mkv', 'mp4', 'and', 'vostfr', 'vf', 'jap', 'ita', 'esp', 'latino',
}
_ROMAN = {2: 'ii', 3: 'iii', 4: 'iv', 5: 'v', 6: 'vi'}


def name_tokens(text: str) -> list:
    """Lowercase ASCII words, long romaji vowels folded (Shoutai = Shotai)."""
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()
    t = t.replace('&', ' and ')
    t = re.sub(r'ou|oo', 'o', t)
    t = re.sub(r'uu', 'u', t)
    return [w for w in re.split(r'[^a-z0-9]+', t) if w and w not in _NOISE]


def _bare(title: str) -> str:
    """Title without extension and bracketed tags; dots as spaces if it has none."""
    t = re.sub(r'\.(mkv|mp4|avi)$', '', title.strip(), flags=re.I)
    if ' ' not in t:                                   # One.Piece.EP1156 style
        t = re.sub(r'[._]', ' ', t)
    return re.sub(r'\[[^\]]*\]|\([^)]*\)|\{[^}]*\}|【[^】]*】', ' ', t)


def _name_end(t: str) -> int:
    end = len(t)
    for cut in _NAME_CUTS:
        m = cut.search(t)
        if m:
            end = min(end, m.start())
    return end


def show_name(title: str) -> str:
    """The show-name part of a release title."""
    t = _bare(title)
    return t[:_name_end(t)]


def episode_marker(title: str):
    """Episode number written where an episode number goes: S01E05, or right
    after the show name (" - 05", " EP05", " #05"). Unlike
    extract_episode_number, never a number from the tags ("10-bit", "[1996]")."""
    m = re.search(r'\bS\d{1,2}E(\d{1,4})\b', title, re.I)
    if m:
        return int(m.group(1))
    t = _bare(title)
    m = re.match(r'\s*(?:[-–~|]\s*)?(?:E[Pp]?\s*|Ep(?:isode)?\.?\s*|#)?(\d{1,4})(?:v\d)?(?![\dp])',
                 t[_name_end(t):], re.I)
    return int(m.group(1)) if m else None


_SPECIAL = r'(?:OVA|OAD|ONA|Specials?|SP|Picture Drama|Recap)s?'


def is_special(title: str) -> bool:
    """An OVA/special rather than a season episode or pack: "Show - OVA 01",
    "Show OVA", "Show - Special 02". A pack that adds them ("Show + OVA",
    "Show & OVA") is still the season."""
    t = _bare(title)
    end = _name_end(t)
    if re.match(rf'\s*(?:[-–~|]\s*)?{_SPECIAL}\b', t[end:], re.I):
        return True
    name = t[:end].strip()
    return bool(re.search(rf'\s{_SPECIAL}\s*\d*$', name, re.I)) and not re.search(r'[+&]', name)


def release_group(title: str) -> str:
    m = re.match(r'\s*\[([^\]]+)\]', title)
    return m.group(1).strip() if m else ''


def title_matches(release_title: str, names, season: int = 1) -> bool:
    """Is this release of the show called any of `names`? (season checked elsewhere)"""
    got = name_tokens(show_name(release_title))
    if not got:
        return False
    variants = [got]
    if len(got) > 1 and got[-1].isdigit():             # "Show 05" with no dash
        variants.append(got[:-1])
    for name in names:
        want = name_tokens(name or '')
        if not want:
            continue
        for v in variants:
            if v == want:
                return True
            # "Genshiken 2" / "Show II" for season 2
            if season > 1 and v[:len(want)] == want and v[len(want):] in ([str(season)], [_ROMAN.get(season)]):
                return True
    return False


def season_in_name(release_title: str, names) -> int | None:
    """Season given as a bare number after the name ("Genshiken 2"), if any."""
    got = name_tokens(show_name(release_title))
    for name in names:
        want = name_tokens(name or '')
        if want and len(got) == len(want) + 1 and got[:len(want)] == want:
            tail = got[-1]
            if tail.isdigit() and 1 < int(tail) < 10:
                return int(tail)
            for n, r in _ROMAN.items():
                if tail == r:
                    return n
    return None


def episode_range(title: str):
    """(first, last) for a batch named like "01-12", "E01~E24", "1 to 13"; else None."""
    t = re.sub(r'[._]', ' ', title) if ' ' not in title.strip() else title
    t = re.sub(r'\b(?:19|20)\d{2}\s*[-~]\s*(?:19|20)\d{2}\b', ' ', t)       # year spans
    t = re.sub(r'\d{3,4}x\d{3,4}|\d\.\d', ' ', t)                           # 1920x1080, 5.1
    m = re.search(r'(?<![\w.])(?:E[Pp]?)?(\d{1,4})\s*(?:-|~|to)\s*(?:E[Pp]?)?(\d{1,4})(?![\w.])', t, re.I)
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    return (a, b) if a < b and b - a < 2000 else None


BATCH_WORDS = re.compile(r'\bbatch\b|\bcomplete\b|\bBD[\s-]?BOX\b|\bcollection\b', re.I)
