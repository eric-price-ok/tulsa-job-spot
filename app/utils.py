from urllib.parse import urlparse


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
