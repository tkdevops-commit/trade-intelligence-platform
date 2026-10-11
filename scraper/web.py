"""Bounded collector for publicly reachable web pages.

This is intentionally an intake primitive, not a browser automation tool.  It
only downloads one public HTTP(S) document, has strict size/time limits, and
rejects loopback and private network destinations.
"""

from __future__ import annotations

import html
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser


MAX_DOCUMENT_BYTES = 1_500_000
USER_AGENT = "TradeIntelligencePlatform/0.1 (internal research intake)"


class CollectionError(ValueError):
    """Raised when a URL cannot safely be collected."""


def validate_public_url(url: str) -> str:
    """Validate an HTTP(S) URL and reject destinations on private networks."""
    candidate = url.strip()
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CollectionError("Enter a complete public http:// or https:// URL.")
    if parsed.username or parsed.password:
        raise CollectionError("URLs containing credentials are not supported.")
    if parsed.port and parsed.port not in {80, 443}:
        raise CollectionError("Only standard public web ports (80 and 443) are supported.")

    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, None)}
    except socket.gaierror as error:
        raise CollectionError("The hostname could not be resolved.") from error
    if not addresses:
        raise CollectionError("The hostname could not be resolved.")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise CollectionError("Private, local, and reserved network addresses cannot be collected.")
    return candidate


class _PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        validate_public_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta" and attributes.get("name", "").lower() == "description":
            self.description = attributes.get("content", "")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        cleaned = " ".join(data.split())
        if cleaned:
            self.parts.append(cleaned)
            if self._in_title:
                self.title += f" {cleaned}"


def collect_page(url: str, timeout_seconds: int = 20) -> dict[str, str | int]:
    """Fetch and extract the readable text from one public HTML page."""
    safe_url = validate_public_url(url)
    opener = urllib.request.build_opener(_PublicRedirectHandler())
    request = urllib.request.Request(safe_url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise CollectionError(f"This URL returned {content_type}, not an HTML page.")
            data = response.read(MAX_DOCUMENT_BYTES + 1)
            if len(data) > MAX_DOCUMENT_BYTES:
                raise CollectionError("The page is larger than the 1.5 MB collection limit.")
            charset = response.headers.get_content_charset() or "utf-8"
            final_url = validate_public_url(response.geturl())
    except urllib.error.HTTPError as error:
        raise CollectionError(f"The site returned HTTP {error.code}.") from error
    except urllib.error.URLError as error:
        raise CollectionError(f"Could not reach the site: {error.reason}") from error

    try:
        document = data.decode(charset, errors="replace")
    except LookupError:
        document = data.decode("utf-8", errors="replace")
    parser = _TextExtractor()
    parser.feed(document)
    text = " ".join(parser.parts)
    title = " ".join(html.unescape(parser.title).split()) or urllib.parse.urlsplit(final_url).hostname or "Untitled page"
    description = " ".join(html.unescape(parser.description).split())
    return {"url": final_url, "title": title[:500], "description": description[:1000], "text": text[:100_000], "bytes": len(data)}
