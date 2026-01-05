from __future__ import annotations

import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from ars_client import ArsTechnicaRSSClient
from lark_client import LarkClient
from llm_utils import (
    LLMClient,
    generate_backend_architect_coaching,
    generate_english_learning,
    generate_japanese_learning,
)
from netflix_client import NetflixTechBlogRSSClient
from rss_client import JapaneseNewsItem, JapaneseRSSClient


def load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def build_english_section(data: Dict[str, str]) -> Dict[str, str]:
    summary_en = data.get("summary_en", "").strip()
    summary_zh = data.get("summary_zh", "").strip()
    return {
        "summary_en": summary_en or "(empty)",
        "summary_zh": summary_zh or "(empty)",
    }


def build_japanese_section(
    news_items: List[JapaneseNewsItem], data: Dict[str, str]
) -> Dict[str, str]:
    news_lines = []
    romaji = data.get("news_romaji", "").strip()
    for item in news_items:
        link_part = f"[原文链接]({item.link})" if item.link else ""
        romaji_part = f"\n  ローマ音: {romaji}" if romaji else ""
        news_lines.append(
            f"- **{item.title}**\n  {item.content}{romaji_part}\n  {link_part}".strip()
        )
    news_text = "\n\n".join(news_lines) if news_lines else "暂无新闻抓取。"

    translation = data.get("translation", "").strip()

    vocab_lines = []
    for entry in data.get("vocabulary", []):
        word = entry.get("word", "")
        romaji_word = entry.get("romaji", "").strip()
        display_word = f"{word} ({romaji_word})" if romaji_word else word
        pos = entry.get("part_of_speech", "")
        meaning = entry.get("meaning_zh", "")
        vocab_lines.append(f"- **{display_word}** ({pos}): {meaning}")
    vocab_text = "\n".join(vocab_lines) if vocab_lines else "暂无词汇整理。"

    grammar_lines = []
    for entry in data.get("grammar", []):
        title = entry.get("title", "")
        desc = entry.get("description", "")
        grammar_lines.append(f"- **{title}**: {desc}")
    grammar_text = "\n".join(grammar_lines) if grammar_lines else "暂无语法说明。"

    return {
        "news": news_text,
        "translation": translation,
        "vocabulary": vocab_text,
        "grammar": grammar_text,
    }


def build_backend_section(data: Dict[str, str], *, article_title: str, article_url: str) -> str:
    topic = (data.get("topic") or article_title).strip() or article_title

    core_chunks = data.get("core_chunks") or []
    chunk_lines: List[str] = []
    for entry in core_chunks[:3]:
        en = (entry.get("en") or "").strip()
        zh = (entry.get("zh") or "").strip()
        if not en:
            continue
        display = f"- `{en}` ({zh})" if zh else f"- `{en}`"
        chunk_lines.append(display)
    chunks_block = "\n".join(chunk_lines) if chunk_lines else "(empty)"

    logic = data.get("logic_connector") or {}
    logic_en = (logic.get("en") or "").strip()
    logic_zh = (logic.get("zh") or "").strip()
    logic_block = "(empty)"
    if logic_en:
        logic_block = f"`{logic_en}` ({logic_zh})" if logic_zh else f"`{logic_en}`"

    interview = data.get("mock_interview") or {}
    question = (interview.get("question") or "").strip() or "(empty)"
    answer = (interview.get("answer") or "").strip() or "(empty)"

    return f"""### {topic}
[Source]({article_url})

Core Chunks (核心语块):
{chunks_block}

Logic Connector (逻辑连接):
{logic_block}

Mock Interview (面试模拟):
- Q: {question}
- A: {answer}
""".strip()


def compose_markdown(
    entry_date: str,
    english_section: Dict[str, str],
    backend_section: str,
    japanese_sections: Dict[str, str],
) -> str:
    return f"""## {entry_date}

### English Learning
{english_section["summary_en"]}

### English Translation (中文翻译)
{english_section["summary_zh"]}

### Backend Architect English Coach
{backend_section}

### Japanese News
{japanese_sections["news"]}

### Japanese Translation
{japanese_sections["translation"]}

### Japanese Vocabulary
{japanese_sections["vocabulary"]}

### Japanese Grammar
{japanese_sections["grammar"]}
""".strip()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s"
    )
    project_root = Path(__file__).resolve().parent
    config = load_config(project_root / "config.json")
    timeout = config.get("request_timeout", 15)

    logging.info("Starting daily language learning task")

    ars_client = ArsTechnicaRSSClient(
        feed_url=config.get("english_rss_url", "https://feeds.arstechnica.com/arstechnica/index"),
        timeout=timeout,
    )
    max_english = config.get("max_english_items", 4)
    english_items = ars_client.fetch_relevant_articles(limit=10, desired=max_english)
    if not english_items:
        raise RuntimeError("Unable to fetch Ars Technica articles.")
    english_prompt = ars_client.build_prompt(english_items)

    rss_client = JapaneseRSSClient(
        feed_url=config["japanese_rss_url"], timeout=timeout
    )
    japanese_candidates = rss_client.fetch_items(limit=5)
    if not japanese_candidates:
        raise RuntimeError("Unable to fetch Japanese RSS news.")
    selected_item = random.choice(japanese_candidates)
    logging.info("Selected Japanese article for study: %s", selected_item.title)
    japanese_prompt = rss_client.build_prompt([selected_item])

    llm_client = LLMClient(
        api_key=config["openai_api_key"],
        model=config.get("openai_model", "gpt-4o-mini"),
    )
    logging.info("Generating English learning content via OpenAI")
    english_data = generate_english_learning(llm_client, english_prompt)

    netflix_client = NetflixTechBlogRSSClient(
        feed_url=config.get("netflix_rss_url", "https://netflixtechblog.com/feed"),
        timeout=timeout,
        max_chars=int(config.get("netflix_max_chars", 12000)),
        ca_bundle=(config.get("netflix_ca_bundle") or None),
        verify=_as_bool(config.get("netflix_verify_ssl"), True),
        allow_insecure_fallback=_as_bool(
            config.get("netflix_allow_insecure_fallback"), False
        ),
        allow_curl_fallback=_as_bool(config.get("netflix_allow_curl_fallback"), True),
    )
    netflix_items = netflix_client.fetch_latest(limit=1)
    if not netflix_items:
        raise RuntimeError("Unable to fetch Netflix Tech Blog article.")
    latest_netflix = netflix_items[0]
    logging.info("Generating backend coaching content via OpenAI")
    backend_data = generate_backend_architect_coaching(
        llm_client,
        article_title=latest_netflix.title,
        article_url=latest_netflix.link,
        article_text=latest_netflix.content,
    )

    logging.info("Generating Japanese learning content via OpenAI")
    japanese_data = generate_japanese_learning(llm_client, japanese_prompt)

    english_section = build_english_section(english_data)
    backend_section = build_backend_section(
        backend_data, article_title=latest_netflix.title, article_url=latest_netflix.link
    )
    japanese_sections = build_japanese_section([selected_item], japanese_data)

    today = datetime.now().strftime("%Y-%m-%d")
    new_entry = compose_markdown(today, english_section, backend_section, japanese_sections)

    month_title = datetime.now().strftime("Daily Language Learning %Y-%m")
    app_id = config.get("lark_app_id")
    app_secret = config.get("lark_app_secret")
    if not app_id or not app_secret:
        raise ValueError(
            "Missing Lark credentials. Provide lark_app_id and lark_app_secret in config.json."
        )
    lark_client = LarkClient(
        app_id=app_id,
        app_secret=app_secret,
        root_folder_token=config["lark_folder_token"],
        timeout=timeout,
    )
    document_token = lark_client.ensure_document(month_title)
    lark_client.prepend_content(document_token, new_entry)

    logging.info("Daily content appended to document '%s'", month_title)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.exception("Daily language learning task failed: %s", exc)
        raise
