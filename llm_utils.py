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
        "You are an assistant that writes concise, real-world English summaries "
        "based on actual technology news for intermediate learners."
    )
    user_prompt = f"""
Use the following technology news to create an English summary and a Chinese translation of that summary.

News:
\"\"\"{news_text}\"\"\"

Requirements:
- Write a natural 150-200 word English summary (summary_en) that is easy to read but still professional.
- Provide a faithful Chinese translation of the English summary (summary_zh).
- Do NOT include any vocabulary list.
- Respond as JSON with this structure:
{{
  "summary_en": "...",
  "summary_zh": "..."
}}
"""
    raw = client.chat(system_prompt, user_prompt, response_format="json_object")
    return _parse_json_response(raw)


def generate_backend_architect_coaching(
    client: LLMClient,
    *,
    article_title: str,
    article_url: str,
    article_text: str,
) -> Dict[str, Any]:
    system_prompt = (
        "You are a senior backend architect English coach. "
        "You teach practical, interview-ready English by extracting reusable technical phrases "
        "from real engineering articles."
    )
    user_prompt = f"""
You are given a real engineering article.

Title: {article_title}
URL: {article_url}

Article (full text):
\"\"\"{article_text}\"\"\"

Please generate content using this logic:

1) Extract 3 backend Core Tech Chunks (core_chunks).
   - Each must be a verb-object phrase or an adjective phrase.
   - Strictly forbid single generic words.
   - Make them specific to backend / distributed systems / data / reliability / performance.
   - Provide Chinese meaning for each.

2) Extract 1 Logic Connector (logic_connector) used to express trade-offs or causality in architecture.
   - Provide Chinese meaning.

3) Design 1 Mock Interview Q&A (mock_interview).
   - The question is about backend architecture.
   - The answer MUST use all 3 core chunks and the logic connector.
   - The answer MUST follow STAR: Situation, Task, Action, Result.

Output constraints:
- Write the chunks and connector in English.
- Keep each chunk concise (prefer <= 7 words if possible).
- Respond as JSON with this structure:
{{
  "topic": "...",
  "core_chunks": [
    {{"en": "...", "zh": "..."}}
  ],
  "logic_connector": {{"en": "...", "zh": "..."}},
  "mock_interview": {{"question": "...", "answer": "..."}}
}}
"""
    raw = client.chat(system_prompt, user_prompt, response_format="json_object")
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
- Provide Hepburn-style romaji for the entire Japanese article (news_romaji) so learners can read it out loud.
- Extract 8-12 important Japanese words found in the news. For each entry include the original word, its romaji reading, part_of_speech, and Chinese meaning.
- Explain 2-3 grammar points from JLPT N5-N3 level that actually appear in the article, referencing the sentence fragments where they occur.
- Respond in JSON with this format:
{{
  "news_romaji": "full romaji transcription of the article",
  "translation": "full Chinese translation in Markdown paragraphs",
  "vocabulary": [
    {{"word": "...", "romaji": "...", "part_of_speech": "...", "meaning_zh": "..."}}
  ],
  "grammar": [
    {{"title": "...", "description": "explain usage and give example from text"}}
  ]
}}
"""
    raw = client.chat(system_prompt, user_prompt)
    return _parse_json_response(raw)
