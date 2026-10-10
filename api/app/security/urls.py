"""URL validation and normalization utilities."""

from urllib.parse import urlparse, urlunparse


def normalize_url(raw_url: str) -> str:
    """Normalize a URL to a canonical form for deduplication.

    Steps:
    - Lowercase scheme and host
    - Remove default ports (80 for http, 443 for https)
    - Remove trailing slash from path (unless path is just '/')
    - Remove fragment
    - Sort query parameters
    """
    parsed = urlparse(raw_url)

    # Only allow http/https
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {scheme}")

    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("URL must have a hostname")

    # Remove default ports
    port = parsed.port
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None

    netloc = host
    if port:
        netloc = f"{host}:{port}"

    # Normalize path
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # Sort query parameters for consistent deduplication
    query = parsed.query
    if query:
        params = sorted(query.split("&"))
        query = "&".join(params)

    # Drop fragment
    return urlunparse((scheme, netloc, path, parsed.params, query, ""))


def validate_url(raw_url: str) -> str:
    """Validate that a URL is well-formed http(s) and return the normalized form."""
    raw_url = raw_url.strip()
    if not raw_url:
        raise ValueError("URL cannot be empty")

    # Add scheme if missing
    if not raw_url.startswith(("http://", "https://")):
        raw_url = "https://" + raw_url

    return normalize_url(raw_url)
