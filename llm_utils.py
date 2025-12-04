from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import requests


class LLMClient:
    """Thin wrapper around OpenAI-compatible chat completions API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: int = 60,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat(self, system_prompt: str, user_prompt: str, response_format: Optional[str] = "json_object") -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        if response_format:
            payload["response_format"] = {"type": response_format}

        logging.debug("Sending prompt to OpenAI model %s", self.model)
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code >= 400:
            logging.error("OpenAI API error %s: %s", resp.status_code, resp.text[:500])
            resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return content


def _parse_json_response(raw: str) -> Dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logging.error("Failed to parse LLM JSON response: %s\nContent: %s", exc, raw)
        raise


def generate_english_learning(client: LLMClient, news_text: str) -> Dict[str, Any]:
    system_prompt = (
        "You are an assistant that prepares concise, real-world English learning material "
        "for intermediate learners based on actual technology news."
    )
    user_prompt = f"""
Use the following technology news to create English learning material.
News:
\"\"\"{news_text}\"\"\"

Requirements:
- Write a natural 150-200 word summary that is easy to read but still professional.
- Provide a vocabulary list of 10-15 words. Each entry must contain the word, an English definition, a Chinese explanation, and a short English example sentence.
- Return JSON with this structure:
{{
  "summary": "paragraphs in Markdown",
  "vocabulary": [
    {{"word": "...", "definition_en": "...", "definition_zh": "...", "example": "..."}}
  ]
}}
"""
    raw = client.chat(system_prompt, user_prompt)
    return _parse_json_response(raw)


def generate_japanese_learning(client: LLMClient, news_text: str) -> Dict[str, Any]:
    system_prompt = (
        "You are a bilingual Japanese-Chinese editor who creates study notes from real Japanese news."
    )
    user_prompt = f"""
Use the real Japanese news below to produce bilingual study notes.
News:
\"\"\"{news_text}\"\"\"

Requirements:
- Translate the full text to Chinese.
- Extract 8-12 important Japanese words found in the news. Provide word, part_of_speech, and Chinese meaning.
- Explain 2-3 grammar points from JLPT N5-N3 level that actually appear in the article, referencing the sentence fragments where they occur.
- Respond in JSON with this format:
{{
  "translation": "full Chinese translation in Markdown paragraphs",
  "vocabulary": [
    {{"word": "...", "part_of_speech": "...", "meaning_zh": "..."}}
  ],
  "grammar": [
    {{"title": "...", "description": "explain usage and give example from text"}}
  ]
}}
"""
    raw = client.chat(system_prompt, user_prompt)
    return _parse_json_response(raw)
