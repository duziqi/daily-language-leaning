from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional
from xml.etree import ElementTree as ET

import requests

KEYWORDS = [
    "ai",
    "artificial intelligence",
    "machine learning",
    "neural",
    "ml",
    "llm",
    "programming",
    "developer",
    "coding",
    "software",
    "algorithm",
    "python",
    "javascript",
]


@dataclass
class ArsArticle:
    title: str
    link: str
    summary: str

    def formatted(self) -> str:
        return f"{self.title}\n{self.summary}\nLink: {self.link}"


class ArsTechnicaRSSClient:
    """Fetches and filters Ars Technica articles for AI/programming news."""

    def __init__(
        self,
        feed_url: str = "https://feeds.arstechnica.com/arstechnica/index",
        session: Optional[requests.Session] = None,
        timeout: int = 10,
    ):
        self.feed_url = feed_url
        self.session = session or requests.Session()
        self.timeout = timeout

    def fetch_articles(self, limit: int = 10) -> List[ArsArticle]:
        logging.debug("Fetching Ars Technica RSS from %s", self.feed_url)
        resp = self.session.get(self.feed_url, timeout=self.timeout)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        channel = root.find("channel")
        if channel is None:
            raise ValueError("Invalid RSS feed: missing channel element")

        articles: List[ArsArticle] = []
        for item in channel.findall("item"):
            title = (item.findtext("title") or "").strip()
            description = (item.findtext("description") or "").strip()
            link = (item.findtext("link") or "").strip()
            if not title or not description:
                continue
            articles.append(ArsArticle(title=title, link=link, summary=description))
            if len(articles) >= limit:
                break
        return articles

    def _is_relevant(self, article: ArsArticle) -> bool:
        haystack = f"{article.title} {article.summary}".lower()
        return any(keyword in haystack for keyword in KEYWORDS)

    def fetch_relevant_articles(self, limit: int = 10, desired: int = 4) -> List[ArsArticle]:
        articles = self.fetch_articles(limit=limit)
        relevant = [article for article in articles if self._is_relevant(article)]
        if not relevant:
            logging.warning(
                "No Ars Technica articles matched AI/programming keywords; falling back to latest items."
            )
            relevant = articles
        return relevant[:desired]

    def build_prompt(self, articles: List[ArsArticle]) -> str:
        if not articles:
            raise ValueError("No Ars Technica articles provided.")
        return "\n\n".join(article.formatted() for article in articles)
