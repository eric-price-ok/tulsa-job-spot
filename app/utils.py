import re
from urllib.parse import urlparse

_LEGAL_SUFFIX_RE = re.compile(
    r",?\s*\b(?:P\.?L\.?L\.?C|L\.?L\.?C|L\.?L\.?P|P\.?L\.?C|PLLC|LLP|LLC|PLC|L\.?P|LP|Inc|Ltd|Corp|Co|P\.?A|P\.?C)\.?\s*$",
    re.IGNORECASE,
)


def generate_slug(name: str) -> str:
    text = _LEGAL_SUFFIX_RE.sub("", name).strip()
    text = text.lower()
    text = re.sub(r"['’‘]", "", text)  # strip apostrophes before hyphenating
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "company"


def sanitize_url(url: str | None) -> str | None:
    """Accept only http/https URLs; return None for anything else."""
    if not url:
        return None
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return None
        return url.strip()
    except Exception:
        return None


def is_safe_redirect(url: str) -> bool:
    """Return True only for relative paths — no scheme, no host."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        return not parsed.scheme and not parsed.netloc
    except Exception:
        return False
