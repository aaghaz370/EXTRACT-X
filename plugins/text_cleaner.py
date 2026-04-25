"""
text_cleaner.py — Shared caption cleaning utilities for ExtractX.
Applied during both Batch and LiveBatch extraction based on per-user settings.
"""

import re

# ── Compiled regex patterns ─────────────────────────────────────────
_RE_USERNAME  = re.compile(r"@[\w]{3,}", re.IGNORECASE)
_RE_TME_LINK  = re.compile(r"(?:https?://)?t\.me/[\w/+?=&#%@.,-]+", re.IGNORECASE)
_RE_HASHTAG   = re.compile(r"#[\w]+", re.IGNORECASE)
_RE_PHONE     = re.compile(
    r"(?<!\w)"
    r"(\+?\d[\d\s\-().]{7,}\d)"
    r"(?!\w)"
)
_RE_ALL_URL   = re.compile(
    r"https?://[^\s<>\"']+|www\.[^\s<>\"']+"
    r"|t\.me/[\w/+?=&#%@.,-]+",
    re.IGNORECASE
)


def apply_text_clean(text: str, tc: dict) -> str:
    """
    Apply all enabled text cleaning rules to a caption/text string.

    Args:
        text: The original caption/text
        tc:   The user's text_clean settings dict

    Returns:
        Cleaned text with multiple spaces/newlines collapsed.
    """
    if not text or not tc:
        return text

    # Order matters: remove all URLs first before username/tme link cleanup
    # to avoid double-removal artifacts on t.me links.
    if tc.get("remove_all_urls"):
        text = _RE_ALL_URL.sub("", text)

    # Only run t.me-specific remover if all_urls remover is OFF
    # (avoids redundant pass over already-cleaned text)
    elif tc.get("remove_tme_links"):
        text = _RE_TME_LINK.sub("", text)

    if tc.get("remove_usernames"):
        text = _RE_USERNAME.sub("", text)

    if tc.get("remove_hashtags"):
        text = _RE_HASHTAG.sub("", text)

    if tc.get("remove_phones"):
        text = _RE_PHONE.sub("", text)

    # Collapse multiple blank lines into one, strip trailing spaces per line
    lines = [line.rstrip() for line in text.splitlines()]
    # Remove runs of more than 1 blank line
    cleaned_lines = []
    prev_blank = False
    for line in lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        cleaned_lines.append(line)
        prev_blank = is_blank

    return "\n".join(cleaned_lines).strip()
