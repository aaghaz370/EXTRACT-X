"""
text_cleaner.py — Shared caption cleaning utilities for ExtractX.
Applied during both Batch and LiveBatch extraction based on per-user settings.
"""

import re

# ── Compiled regex patterns ─────────────────────────────────────────

# @username: must be at least 3 chars after @
_RE_USERNAME = re.compile(r"@[\w]{3,}", re.IGNORECASE)

# t.me links (with or without https://)
_RE_TME_LINK = re.compile(
    r"(?:https?://)?t\.me/[\w/+?=&#%@.,\-]+",
    re.IGNORECASE
)

# Hashtags
_RE_HASHTAG = re.compile(r"#[\w]+", re.IGNORECASE)

# Phone numbers: +91 style, at least 7 digits
_RE_PHONE = re.compile(
    r"(?<!\w)(\+?\d[\d\s\-().]{7,}\d)(?!\w)"
)

# All URLs — catches:
#   https://example.com/path
#   http://example.com
#   www.example.com/path
#   example.com/some/path   (bare domain with at least one slash)
#   t.me/...
_RE_ALL_URL = re.compile(
    r"(?:"
        r"https?://[^\s<>\"')\]]+"           # http:// or https:// links
        r"|www\.[^\s<>\"')\]]+"              # www. links
        r"|t\.me/[\w/+?=&#%@.,\-]+"         # t.me links
        r"|[\w\-]+\.(?:com|net|org|io|in|co|me|xyz|info|tv|app|dev|shop|site|store|online|club|live|pro|ai|cc|gg|vip|link|top|biz|us|uk|eu|ru|jp|de|fr|pk|bd)[/\w.?=&#%@,\-]*"
    r")",
    re.IGNORECASE
)

# Lines that look like password/credential lines — protect them
_RE_PASSWORD_LINE = re.compile(
    r"^\s*(?:pass(?:word)?|pwd|passwd|pin|key|code|secret|login|user(?:name)?)\s*[:\-=]\s*.+",
    re.IGNORECASE
)


def _build_exempt_patterns(caption_rules: dict) -> list:
    """
    Build a list of literal strings the user wants to keep untouched:
    — prefix text
    — suffix text  
    — replacement NEW values (what they want to insert)
    These must never be cleaned by text_cleaner.
    """
    exempt = []
    if not caption_rules:
        return exempt
    p = caption_rules.get("prefix", "")
    s = caption_rules.get("suffix", "")
    if p: exempt.append(p.strip())
    if s: exempt.append(s.strip())
    for new_val in caption_rules.get("replacements", {}).values():
        if new_val: exempt.append(new_val.strip())
    return [e for e in exempt if e]


def _mask_exempt(text: str, exempt_strings: list) -> tuple:
    """
    Temporarily replace exempt strings with numbered placeholders
    so cleaners never touch them. Returns (masked_text, restore_map).
    """
    restore_map = {}
    for i, s in enumerate(exempt_strings):
        placeholder = f"\x00EXEMPT{i}\x00"
        if s in text:
            text = text.replace(s, placeholder)
            restore_map[placeholder] = s
    return text, restore_map


def _restore_exempt(text: str, restore_map: dict) -> str:
    for placeholder, original in restore_map.items():
        text = text.replace(placeholder, original)
    return text


def apply_text_clean(text: str, tc: dict, caption_rules: dict = None) -> str:
    """
    Apply all enabled text cleaning rules to a caption/text string.

    Args:
        text:          The original caption/text
        tc:            The user's text_clean settings dict
        caption_rules: The user's caption_rules (prefix/suffix/replacements)
                       — their content is exempted from cleaning.

    Returns:
        Cleaned text with multiple spaces/newlines collapsed.
    """
    if not text or not tc:
        return text

    # 1. Build exempt placeholders for user's own prefix/suffix/replacements
    exempt_strings = _build_exempt_patterns(caption_rules or {})
    text, restore_map = _mask_exempt(text, exempt_strings)

    # 2. Process line by line — skip password lines entirely
    lines = text.splitlines()
    processed_lines = []
    for line in lines:
        if _RE_PASSWORD_LINE.match(line):
            # Password/credential lines are sacred — never touch them
            processed_lines.append(line)
            continue

        # Apply rules to this line
        if tc.get("remove_all_urls"):
            line = _RE_ALL_URL.sub("", line)
        elif tc.get("remove_tme_links"):
            line = _RE_TME_LINK.sub("", line)

        if tc.get("remove_usernames"):
            line = _RE_USERNAME.sub("", line)

        if tc.get("remove_hashtags"):
            line = _RE_HASHTAG.sub("", line)

        if tc.get("remove_phones"):
            line = _RE_PHONE.sub("", line)

        processed_lines.append(line)

    text = "\n".join(processed_lines)

    # 3. Restore exempted strings
    text = _restore_exempt(text, restore_map)

    # 4. Collapse runs of blank lines, strip trailing spaces per line
    lines = [ln.rstrip() for ln in text.splitlines()]
    cleaned_lines = []
    prev_blank = False
    for line in lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        cleaned_lines.append(line)
        prev_blank = is_blank

    return "\n".join(cleaned_lines).strip()
