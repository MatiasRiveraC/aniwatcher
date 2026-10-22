import re


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
