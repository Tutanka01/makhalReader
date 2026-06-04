"""
Tests for net_guard.py — Story 3.2 SSRF protection guard.

Run:
    python test_net_guard.py
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

# Pre-seed httpx so net_guard can import it even when httpx is not installed
sys.modules["httpx"] = MagicMock()

sys.path.insert(0, __file__)

from net_guard import SSRFBlockedError, check_url

_PASS = 0
_FAIL = 0


def _ok(name: str) -> None:
    global _PASS
    _PASS += 1
    print(f"  \u2705  {name}")


def _fail(name: str, msg: str) -> None:
    global _FAIL
    _FAIL += 1
    print(f"  \u274c  {name}: {msg}")


def _assert_raises(name: str, exc_type: type, func, *args, **kwargs) -> None:
    try:
        func(*args, **kwargs)
        _fail(name, f"expected {exc_type.__name__}, no exception raised")
    except exc_type:
        _ok(name)
    except Exception as e:
        _fail(name, f"expected {exc_type.__name__}, got {type(e).__name__}: {e}")


def _assert_ok(name: str, func, *args, **kwargs) -> None:
    try:
        func(*args, **kwargs)
        _ok(name)
    except Exception as e:
        _fail(name, f"unexpected exception: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Test 1: Public HTTPS URL allowed
# ══════════════════════════════════════════════════════════════════════════════

def test_public_https_allowed() -> None:
    with (
        patch("socket.getaddrinfo", return_value=[(0, 0, 0, "", ("8.8.8.8", 443))]),
        patch("net_guard._check_redirect_loop") as _,
    ):
        _assert_ok("public HTTPS URL allowed", check_url, "https://api.openalex.org/works")


# ══════════════════════════════════════════════════════════════════════════════
# Test 2: Private IP range blocked (192.168.x.x)
# ══════════════════════════════════════════════════════════════════════════════

def test_private_ip_blocked() -> None:
    with patch("socket.getaddrinfo", return_value=[(0, 0, 0, "", ("192.168.1.1", 80))]):
        _assert_raises(
            "private IP (192.168.x.x) blocked",
            SSRFBlockedError,
            check_url, "https://192.168.1.1/secret",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Test 3: Link-local / AWS metadata blocked
# ══════════════════════════════════════════════════════════════════════════════

def test_link_local_blocked() -> None:
    with patch("socket.getaddrinfo", return_value=[(0, 0, 0, "", ("169.254.169.254", 443))]):
        _assert_raises(
            "link-local IP (169.254.x.x) blocked",
            SSRFBlockedError,
            check_url, "https://169.254.169.254/latest/meta-data/",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Test 4: HTTP scheme blocked (HTTPS required)
# ══════════════════════════════════════════════════════════════════════════════

def test_http_scheme_blocked() -> None:
    _assert_raises(
        "HTTP (not HTTPS) blocked",
        SSRFBlockedError,
        check_url, "http://example.com/feed",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Test 5: Redirect loop detected
# ══════════════════════════════════════════════════════════════════════════════

def test_redirect_loop_blocked() -> None:
    mock_resp = MagicMock()
    mock_resp.is_redirect = True
    mock_resp.is_permanent_redirect = False
    mock_resp.headers = {"Location": "https://example.com/loop"}

    with (
        patch("socket.getaddrinfo", return_value=[(0, 0, 0, "", ("93.184.216.34", 443))]),
        patch("httpx.head", return_value=mock_resp) as mock_head,
    ):
        _assert_raises(
            "redirect loop blocked",
            SSRFBlockedError,
            check_url, "https://example.com/loop", max_redirects=3,
        )
        # Was called at least once (until loop detected)
        mock_head.assert_called()


# ══════════════════════════════════════════════════════════════════════════════
# Test 6: 10.x.x.x range blocked
# ══════════════════════════════════════════════════════════════════════════════

def test_ten_dot_range_blocked() -> None:
    with patch("socket.getaddrinfo", return_value=[(0, 0, 0, "", ("10.0.0.6", 443))]):
        _assert_raises(
            "10.x.x.x IP blocked",
            SSRFBlockedError,
            check_url, "https://10.0.0.6/internal",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Test 7: 172.16-31.x.x range blocked
# ══════════════════════════════════════════════════════════════════════════════

def test_172_dot_range_blocked() -> None:
    with patch("socket.getaddrinfo", return_value=[(0, 0, 0, "", ("172.20.0.2", 443))]):
        _assert_raises(
            "172.16-31.x.x IP blocked",
            SSRFBlockedError,
            check_url, "https://172.20.0.2/service",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Test 8: Localhost (127.x.x.x) blocked
# ══════════════════════════════════════════════════════════════════════════════

def test_localhost_blocked() -> None:
    with patch("socket.getaddrinfo", return_value=[(0, 0, 0, "", ("127.0.0.1", 443))]):
        _assert_raises(
            "localhost blocked",
            SSRFBlockedError,
            check_url, "https://127.0.0.1/api",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Test 9: Exceeding max_redirects raises error
# ══════════════════════════════════════════════════════════════════════════════

def test_max_redirects_exceeded() -> None:
    mock_resp = MagicMock()
    mock_resp.is_redirect = True
    mock_resp.is_permanent_redirect = False

    def _side_effect(url, **kw):
        mock_resp.headers = {"Location": f"https://example.com/redirect/{hash(url)}"}
        return mock_resp

    with (
        patch("socket.getaddrinfo", return_value=[(0, 0, 0, "", ("93.184.216.34", 443))]),
        patch("httpx.head", side_effect=_side_effect),
    ):
        _assert_raises(
            "max redirects exceeded",
            SSRFBlockedError,
            check_url, "https://example.com/start", max_redirects=3,
        )


# ══════════════════════════════════════════════════════════════════════════════
# Test 10: Non-http scheme blocked
# ══════════════════════════════════════════════════════════════════════════════

def test_non_http_scheme_blocked() -> None:
    _assert_raises(
        "ftp scheme blocked",
        SSRFBlockedError,
        check_url, "ftp://files.example.com/data",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Test 11: Unresolvable hostname blocked
# ══════════════════════════════════════════════════════════════════════════════

def test_unresolvable_hostname_blocked() -> None:
    with patch("socket.getaddrinfo", side_effect=socket.gaierror):
        _assert_raises(
            "unresolvable hostname blocked",
            SSRFBlockedError,
            check_url, "https://this-does-not-exist.example/",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import socket

    test_public_https_allowed()
    test_private_ip_blocked()
    test_link_local_blocked()
    test_http_scheme_blocked()
    test_redirect_loop_blocked()
    test_ten_dot_range_blocked()
    test_172_dot_range_blocked()
    test_localhost_blocked()
    test_max_redirects_exceeded()
    test_non_http_scheme_blocked()
    test_unresolvable_hostname_blocked()

    total = _PASS + _FAIL
    print(f"\n{'='*40}")
    print(f"  {_PASS}/{total} passed")
    if _FAIL:
        print(f"  \u274c  {_FAIL} FAILED")
        sys.exit(1)
    else:
        print(f"  \u2705  ALL PASSED")
