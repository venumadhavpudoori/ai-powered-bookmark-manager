"""SSRF protection: validate that a URL does not resolve to a private/reserved IP.

Non-negotiable rules (from CLAUDE.md):
- http/https only
- Resolve DNS and reject loopback, private, link-local, reserved, cloud-metadata IPs
- Connect to the validated IP
- Re-validate every redirect (max 3)
- 10 s timeout
- 2 MB body cap
- Allow text/html only
- No JS execution
"""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

MAX_REDIRECTS = 3
TIMEOUT_SECONDS = 10
MAX_BODY_BYTES = 2 * 1024 * 1024  # 2 MB
ALLOWED_CONTENT_TYPES = {"text/html"}

# Cloud metadata endpoints to block explicitly
BLOCKED_HOSTS = {
    "metadata.google.internal",
    "metadata.google.com",
}


def _is_ip_safe(ip_str: str) -> bool:
    """Return True if the IP address is publicly routable (safe to connect to)."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    if addr.is_loopback:
        return False
    if addr.is_private:
        return False
    if addr.is_reserved:
        return False
    if addr.is_link_local:
        return False
    if addr.is_multicast:
        return False

    # Block Shared Address Space / CGNAT (100.64.0.0/10)
    cgnat = ipaddress.ip_network("100.64.0.0/10")
    if addr in cgnat:
        return False

    # Block cloud metadata IP (169.254.169.254)
    if ip_str == "169.254.169.254":
        return False

    # Block IPv6 mapped versions of private IPs
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        return _is_ip_safe(str(addr.ipv4_mapped))

    return True


def _resolve_and_validate(hostname: str) -> str:
    """Resolve hostname to IP and validate it is safe. Returns the resolved IP."""
    if hostname.lower() in BLOCKED_HOSTS:
        raise SSRFError(f"Blocked host: {hostname}")

    # Check if hostname is already an IP
    try:
        ip = ipaddress.ip_address(hostname)
        if not _is_ip_safe(str(ip)):
            raise SSRFError(f"IP address {hostname} is not allowed")
        return hostname
    except ValueError:
        pass  # Not an IP, resolve DNS

    try:
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFError(f"DNS resolution failed for {hostname}") from exc

    if not results:
        raise SSRFError(f"No DNS results for {hostname}")

    # Check ALL resolved IPs (prevent DNS rebinding)
    resolved_ip = None
    for family, _type, _proto, _canonname, sockaddr in results:
        ip_str = sockaddr[0]
        if not _is_ip_safe(ip_str):
            raise SSRFError(f"Resolved IP {ip_str} for {hostname} is not allowed")
        if resolved_ip is None:
            resolved_ip = ip_str

    return resolved_ip  # type: ignore[return-value]


class SSRFError(Exception):
    """Raised when a URL fails SSRF validation."""


async def safe_fetch(url: str) -> tuple[str, str | None]:
    """Fetch a URL with full SSRF protection.

    Returns:
        Tuple of (html_content, final_url).

    Raises:
        SSRFError: If the URL fails any security check.
        httpx.HTTPError: On network errors.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFError(f"Unsupported scheme: {parsed.scheme}")

    current_url = url
    redirects_followed = 0

    async with httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS,
        follow_redirects=False,  # We handle redirects manually
        verify=True,
    ) as client:
        while True:
            parsed = urlparse(current_url)
            hostname = parsed.hostname
            if not hostname:
                raise SSRFError("URL has no hostname")

            # Resolve DNS and validate IP
            resolved_ip = _resolve_and_validate(hostname)
            logger.debug("Resolved %s -> %s", hostname, resolved_ip)

            # Build the request URL connecting to the resolved IP
            # Use Host header to maintain the original hostname
            port = parsed.port
            if port:
                base = f"{parsed.scheme}://{resolved_ip}:{port}"
            else:
                base = f"{parsed.scheme}://{resolved_ip}"

            target_url = base + (parsed.path or "/")
            if parsed.query:
                target_url += f"?{parsed.query}"

            headers = {
                "Host": hostname if not port else f"{hostname}:{port}",
                "User-Agent": "RecallAI/1.0 (bookmark manager)",
                "Accept": "text/html",
            }

            response = await client.get(
                target_url,
                headers=headers,
                extensions={"sni_hostname": hostname},  # TLS SNI
            )

            # Handle redirects manually — re-validate each hop
            if response.is_redirect:
                redirects_followed += 1
                if redirects_followed > MAX_REDIRECTS:
                    raise SSRFError(f"Too many redirects (>{MAX_REDIRECTS})")

                location = response.headers.get("location")
                if not location:
                    raise SSRFError("Redirect with no Location header")

                # Resolve relative redirects
                if location.startswith("/"):
                    location = f"{parsed.scheme}://{hostname}{location}"

                redirect_parsed = urlparse(location)
                if redirect_parsed.scheme not in ("http", "https"):
                    raise SSRFError(f"Redirect to unsupported scheme: {redirect_parsed.scheme}")

                current_url = location
                continue

            response.raise_for_status()

            # Validate content type
            content_type = response.headers.get("content-type", "")
            mime = content_type.split(";")[0].strip().lower()
            if mime not in ALLOWED_CONTENT_TYPES:
                raise SSRFError(f"Content-Type '{mime}' is not allowed (expected text/html)")

            # Enforce body size limit
            body = response.content
            if len(body) > MAX_BODY_BYTES:
                raise SSRFError(f"Response body exceeds {MAX_BODY_BYTES} bytes")

            return body.decode("utf-8", errors="replace"), current_url
