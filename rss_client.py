from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional
from xml.etree import ElementTree as ET

import requests


@dataclass
class JapaneseNewsItem:
    title: str
    link: str
    published_at: datetime
    content: str

    def formatted(self) -> str:
        return f"{self.title}\n{self.content}\nLink: {self.link}"


class JapaneseRSSClient:
    """Fetches latest Japanese news articles from an RSS feed."""

    def __init__(self, feed_url: str, session: Optional[requests.Session] = None, timeout: int = 10):
        self.feed_url = feed_url
        self.session = session or requests.Session()
        self.timeout = timeout

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

    def fetch_items(self, limit: int = 1) -> List[JapaneseNewsItem]:
        logging.debug("Fetching Japanese RSS feed from %s", self.feed_url)
        resp = self.session.get(self.feed_url, timeout=self.timeout)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        channel = root.find("channel")
        if channel is None:
            raise ValueError("Invalid RSS feed: missing channel element")

        items: List[JapaneseNewsItem] = []
        for item in channel.findall("item"):
            title = (item.findtext("title") or "").strip()
            description = (item.findtext("description") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date_raw = item.findtext("pubDate")
            pub_date = self._parse_datetime(pub_date_raw)

            if not title or not description:
                continue

            news_item = JapaneseNewsItem(
                title=title,
                link=link,
                published_at=pub_date,
                content=description,
            )
            items.append(news_item)
            if len(items) >= limit:
                break
        return items

    def build_prompt(self, items: List[JapaneseNewsItem]) -> str:
        if not items:
            raise ValueError("No RSS news items fetched.")
        return "\n\n".join(item.formatted() for item in items)
