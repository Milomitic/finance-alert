"""Bounded, unauthenticated article downloads from public Internet addresses.

Resolve each redirect separately and connect to the validated numeric address.
Keeping TLS SNI/certificate verification on the original host avoids a second
DNS lookup (and the usual validate-then-connect DNS rebinding race).
Environment proxies, cookies and automatic redirects are deliberately unused.
"""
from __future__ import annotations

import ipaddress
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit

import urllib3
from urllib3.util import Timeout

_MAX_REDIRECTS = 3


def _public_target(url: str) -> tuple[str, str, int, str, str]:
    if len(url) > 4096 or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        raise ValueError("Invalid article URL")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("Only HTTP(S) article URLs are allowed")
    if parts.username is not None or parts.password is not None or "%" in parts.hostname:
        raise ValueError("Credentials and scoped addresses are not allowed")
    host = parts.hostname.rstrip(".").encode("idna").decode("ascii")
    port = parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80)
    if port != (443 if parts.scheme == "https" else 80):
        raise ValueError("Non-standard article port")
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError("No address for article host")
    for entry in addresses:
        address = ipaddress.ip_address(entry[4][0])
        if not address.is_global or address.is_reserved or address.is_multicast:
            raise ValueError("Non-public article destination")
        if isinstance(address, ipaddress.IPv6Address):
            if (
                address.ipv4_mapped or address.sixtofour or address.teredo
                or address in ipaddress.ip_network("64:ff9b::/96")
                or address in ipaddress.ip_network("64:ff9b:1::/48")
            ):
                raise ValueError("Transition addresses are not allowed")
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return parts.scheme, host, port, str(addresses[0][4][0]), path


def fetch_public_text(url: str, *, max_bytes: int, timeout: float, user_agent: str) -> str:
    """Return at most max_bytes of decoded text; fail closed on unsafe hops.

    The deadline covers redirects and reads. OS DNS resolution retains its
    resolver timeout; it cannot be interrupted by the socket read timeout.
    """
    deadline = time.monotonic() + timeout
    for hop in range(_MAX_REDIRECTS + 1):
        scheme, host, port, address, path = _public_target(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Article time budget exhausted")
        pool_args = {"host": address, "port": port, "retries": False}
        if scheme == "https":
            pool = urllib3.HTTPSConnectionPool(
                **pool_args, server_hostname=host, assert_hostname=host,
                cert_reqs=ssl.CERT_REQUIRED,
            )
        else:
            pool = urllib3.HTTPConnectionPool(**pool_args)
        # Numeric IPv6 hosts need brackets in the HTTP Host header.
        header_host = f"[{host}]" if ":" in host else host
        with pool:
            response = pool.urlopen(
                "GET", path,
                headers={"Host": header_host, "User-Agent": user_agent,
                         "Accept": "text/html,application/xhtml+xml,text/plain",
                         "Accept-Encoding": "identity"},
                redirect=False, retries=False, preload_content=False,
                assert_same_host=False,
                timeout=Timeout(total=remaining, connect=min(2.0, remaining), read=remaining),
            )
            try:
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if not location or hop == _MAX_REDIRECTS:
                        raise ValueError("Article redirect limit")
                    next_url = urljoin(url, location)
                    if scheme == "https" and urlsplit(next_url).scheme != "https":
                        raise ValueError("HTTPS downgrade")
                    url = next_url
                    continue
                if response.status != 200:
                    raise ValueError("Article HTTP failure")
                content_type = response.headers.get("Content-Type", "").lower()
                if not (content_type.startswith("text/") or "application/xhtml+xml" in content_type):
                    raise ValueError("Article is not text")
                # Do not decompress attacker-controlled compressed responses.
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise ValueError("Unexpected compressed article")
                chunks = bytearray()
                while len(chunks) < max_bytes:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Article time budget exhausted")
                    chunk = response.read1(min(8192, max_bytes - len(chunks)), decode_content=False)
                    if not chunk:
                        break
                    chunks.extend(chunk)
                return chunks.decode("utf-8", errors="replace")
            finally:
                response.close()
    raise ValueError("Article redirect limit")
