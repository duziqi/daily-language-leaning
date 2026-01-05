from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import List, Optional, Union
from xml.etree import ElementTree as ET

import requests
from requests import exceptions as requests_exceptions


@dataclass
class NetflixTechBlogItem:
    title: str
    link: str
    published_at: datetime
    content: str


class _HTMLToText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: List[str] = []
        self._in_pre = False

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag in {"p", "div", "section", "article", "br", "hr"}:
            self._chunks.append("\n")
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._chunks.append("\n")
        if tag in {"li"}:
            self._chunks.append("\n- ")
        if tag == "pre":
            self._in_pre = True
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag == "pre":
            self._in_pre = False
            self._chunks.append("\n")
        if tag in {"p", "li"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if not data:
            return
        text = unescape(data)
        if not self._in_pre:
            text = " ".join(text.split())
        self._chunks.append(text)

    def get_text(self) -> str:
        joined = "".join(self._chunks)
        lines = [line.strip() for line in joined.splitlines()]
        compact: List[str] = []
        for line in lines:
            if not line:
                if compact and compact[-1] != "":
                    compact.append("")
                continue
            compact.append(line)
        return "\n".join(compact).strip()


class NetflixTechBlogRSSClient:
    """Fetches latest articles from Netflix Tech Blog RSS feed."""

    CONTENT_NAMESPACES = {
        "content": "http://purl.org/rss/1.0/modules/content/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    def __init__(
        self,
        feed_url: str = "https://netflixtechblog.com/feed",
        fallback_feed_urls: Optional[List[str]] = None,
        session: Optional[requests.Session] = None,
        timeout: int = 10,
        max_chars: int = 12000,
        verify: bool = True,
        ca_bundle: Optional[str] = None,
        allow_insecure_fallback: bool = False,
        allow_curl_fallback: bool = True,
    ):
        self.feed_url = feed_url
        self.fallback_feed_urls = [url for url in (fallback_feed_urls or []) if url]
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_chars = max_chars
        self.verify: Union[bool, str] = ca_bundle if ca_bundle else verify
        self.allow_insecure_fallback = allow_insecure_fallback
        self.allow_curl_fallback = allow_curl_fallback

    def _fetch_via_curl(self) -> bytes:
        timeout = max(1, int(self.timeout))
        cmd = [
            "curl",
            "-fsSL",
            "--max-time",
            str(timeout),
            self.feed_url,
        ]
        result = subprocess.run(cmd, check=False, capture_output=True)
        if result.returncode != 0:
            stderr = (result.stderr or b"").decode("utf-8", errors="replace")
            raise RuntimeError(f"curl failed fetching {self.feed_url}: {stderr[:500]}")
        return result.stdout

    def _parse_datetime(self, value: Optional[str]) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        try:
            dt = parsedate_to_datetime(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (TypeError, ValueError):
            logging.debug("Unable to parse pubDate '%s'", value)
            return datetime.now(timezone.utc)

    @staticmethod
    def _html_to_text(html: str) -> str:
        parser = _HTMLToText()
        parser.feed(html)
        return parser.get_text()

    def _candidate_feed_urls(self) -> List[str]:
        urls = [self.feed_url]
        for url in self.fallback_feed_urls:
            if url not in urls:
                urls.append(url)
        return urls

    def fetch_latest(self, limit: int = 1) -> List[NetflixTechBlogItem]:
        last_error: Optional[Exception] = None
        for url in self._candidate_feed_urls():
            logging.debug("Fetching Netflix Tech Blog RSS from %s", url)
            try:
                resp = self.session.get(url, timeout=self.timeout, verify=self.verify)
                resp.raise_for_status()
                root = ET.fromstring(resp.content)
                return self._parse_items(root, limit=limit)
            except requests_exceptions.SSLError as exc:
                last_error = exc
                if self.allow_insecure_fallback:
                    logging.warning(
                        "SSL verification failed fetching %s; retrying with verify=False (INSECURE).",
                        url,
                    )
                    resp = self.session.get(url, timeout=self.timeout, verify=False)
                    resp.raise_for_status()
                    root = ET.fromstring(resp.content)
                    return self._parse_items(root, limit=limit)
                if self.allow_curl_fallback:
                    logging.warning(
                        "SSL verification failed fetching %s; retrying via system curl.",
                        url,
                    )
                    content = self._fetch_via_curl() if url == self.feed_url else self._fetch_via_curl_url(url)
                    root = ET.fromstring(content)
                    return self._parse_items(root, limit=limit)
                logging.warning("SSL verification failed fetching %s; trying next feed URL.", url)
                continue
            except (requests_exceptions.RequestException, ET.ParseError, RuntimeError) as exc:
                last_error = exc
                logging.warning("Failed fetching/parsing %s; trying next feed URL. (%s)", url, type(exc).__name__)
                continue

        raise RuntimeError(
            f"Unable to fetch Netflix Tech Blog RSS from any configured URL: {self._candidate_feed_urls()}"
        ) from last_error

    def _fetch_via_curl_url(self, url: str) -> bytes:
        timeout = max(1, int(self.timeout))
        cmd = [
            "curl",
            "-fsSL",
            "--max-time",
            str(timeout),
            url,
        ]
        result = subprocess.run(cmd, check=False, capture_output=True)
        if result.returncode != 0:
            stderr = (result.stderr or b"").decode("utf-8", errors="replace")
            raise RuntimeError(f"curl failed fetching {url}: {stderr[:500]}")
        return result.stdout

    def _parse_items(self, root: ET.Element, *, limit: int) -> List[NetflixTechBlogItem]:
        channel = root.find("channel")
        if channel is None:
            raise ValueError("Invalid RSS feed: missing channel element")

        items: List[NetflixTechBlogItem] = []
        for item in channel.findall("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = self._parse_datetime(item.findtext("pubDate"))

            content_html = item.findtext("content:encoded", namespaces=self.CONTENT_NAMESPACES)
            description_html = item.findtext("description")
            raw_html = (content_html or description_html or "").strip()
            content = self._html_to_text(raw_html) if raw_html else ""

            if self.max_chars and len(content) > self.max_chars:
                logging.info(
                    "Netflix article content truncated from %s to %s characters.",
                    len(content),
                    self.max_chars,
                )
                content = content[: self.max_chars].rstrip() + "\n\n...(truncated)"

            if not title or not link:
                continue

            items.append(
                NetflixTechBlogItem(
                    title=title,
                    link=link,
                    published_at=pub_date,
                    content=content,
                )
            )
            if len(items) >= limit:
                break

        return items
