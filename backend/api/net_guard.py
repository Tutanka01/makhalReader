from __future__ import annotations

import ipaddress
import socket
import urllib.parse


class SSRFBlockedError(Exception):
    """Raised when a URL is blocked by the SSRF guard."""


_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_ip(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in _PRIVATE_NETS)
    except ValueError:
        return False


def check_url(url: str, max_redirects: int = 5) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFBlockedError(f"Blocked scheme: {parsed.scheme!r}")
    if parsed.scheme != "https":
        raise SSRFBlockedError("Only HTTPS URLs are allowed")

    host = parsed.hostname
    if not host:
        raise SSRFBlockedError("No hostname in URL")

    try:
        addrs = socket.getaddrinfo(host, 443, family=socket.AF_INET)
        for family, _, _, _, sockaddr in addrs:
            ip = sockaddr[0]
            if _is_private_ip(ip):
                raise SSRFBlockedError(f"Blocked private IP: {ip}")
    except socket.gaierror:
        raise SSRFBlockedError(f"Could not resolve hostname: {host}")

    if max_redirects > 0:
        _check_redirect_loop(url, max_redirects)


def _check_redirect_loop(url: str, max_redirects: int) -> None:
    import httpx

    seen: set[str] = set()
    current = url
    for _ in range(max_redirects + 1):
        if current in seen:
            raise SSRFBlockedError("Redirect loop detected")
        seen.add(current)
        try:
            resp = httpx.head(current, follow_redirects=False, timeout=10.0)
        except httpx.RequestError:
            return
        if resp.is_redirect or resp.is_permanent_redirect:
            location = resp.headers.get("Location")
            if not location:
                return
            current = urllib.parse.urljoin(current, location)
        else:
            return
    raise SSRFBlockedError(f"Exceeded max redirects ({max_redirects})")
