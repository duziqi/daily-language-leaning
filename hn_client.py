from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List, Optional

import requests

HN_TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{story_id}.json"


@dataclass
class HackerNewsStory:
    """Represents a Hacker News story that can be used for prompting."""

    id: int
    title: str
    url: Optional[str]
    text: Optional[str]

    def as_prompt_segment(self) -> str:
        link = self.url or f"https://news.ycombinator.com/item?id={self.id}"
        body = self.text or ""
        return f"- {self.title}\n  Link: {link}\n  Notes: {body}".strip()


class HackerNewsClient:
    """Simple Hacker News API client that fetches top technology stories."""

    def __init__(self, session: Optional[requests.Session] = None, timeout: int = 10):
        self.session = session or requests.Session()
        self.timeout = timeout

    def fetch_top_story_ids(self, limit: int = 30) -> List[int]:
        logging.debug("Fetching top story IDs from Hacker News")
        resp = self.session.get(HN_TOP_STORIES_URL, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise ValueError(f"Unexpected response from HN API: {json.dumps(data)[:200]}")
        return data[:limit]

    def fetch_story(self, story_id: int) -> Optional[HackerNewsStory]:
        try:
            resp = self.session.get(
                HN_ITEM_URL.format(story_id=story_id), timeout=self.timeout
            )
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            logging.warning("Failed to fetch story %s: %s", story_id, exc)
            return None

        if not isinstance(payload, dict) or payload.get("type") != "story":
            return None

        title = payload.get("title")
        url = payload.get("url")
        text = payload.get("text")
        if not title:
            return None

        return HackerNewsStory(id=story_id, title=title, url=url, text=text)

    def fetch_top_stories(self, desired: int = 4) -> List[HackerNewsStory]:
        """Fetch up to `desired` stories, skipping invalid ones."""
        stories: List[HackerNewsStory] = []
        for story_id in self.fetch_top_story_ids(limit=40):
            story = self.fetch_story(story_id)
            if story:
                stories.append(story)
            if len(stories) >= desired:
                break
        return stories

    def build_prompt(self, stories: List[HackerNewsStory]) -> str:
        if not stories:
            raise ValueError("No Hacker News stories available to build a prompt.")
        segments = "\n\n".join(story.as_prompt_segment() for story in stories)
        return (
            "The following are real technology stories taken from Hacker News:\n\n"
            f"{segments}\n\nUse them to craft the learning content."
        )
