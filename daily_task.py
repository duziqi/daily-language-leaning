from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from hn_client import HackerNewsClient, HackerNewsStory
from lark_client import LarkClient, fetch_tenant_access_token
from llm_utils import LLMClient, generate_english_learning, generate_japanese_learning
from rss_client import JapaneseNewsItem, JapaneseRSSClient


def load_config(config_path: Path) -> Dict[str, str]:
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def build_english_section(data: Dict[str, str]) -> str:
    summary = data.get("summary", "").strip()
    vocab_lines = []
    for entry in data.get("vocabulary", []):
        word = entry.get("word", "")
        definition_en = entry.get("definition_en", "")
        definition_zh = entry.get("definition_zh", "")
        example = entry.get("example", "")
        vocab_lines.append(
            f"- **{word}**: {definition_en} / {definition_zh}\n  例句: {example}"
        )
    vocab_text = "\n".join(vocab_lines) if vocab_lines else "暂无词汇。"
    return summary, vocab_text


def build_japanese_section(
    news_items: List[JapaneseNewsItem], data: Dict[str, str]
) -> Dict[str, str]:
    news_lines = []
    for item in news_items:
        link_part = f"[原文链接]({item.link})" if item.link else ""
        news_lines.append(
            f"- **{item.title}**\n  {item.content}\n  {link_part}".strip()
        )
    news_text = "\n\n".join(news_lines) if news_lines else "暂无新闻抓取。"

    translation = data.get("translation", "").strip()

    vocab_lines = []
    for entry in data.get("vocabulary", []):
        word = entry.get("word", "")
        pos = entry.get("part_of_speech", "")
        meaning = entry.get("meaning_zh", "")
        vocab_lines.append(f"- **{word}** ({pos}): {meaning}")
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


def compose_markdown(
    entry_date: str,
    english_summary: str,
    english_vocab: str,
    japanese_sections: Dict[str, str],
) -> str:
    return f"""## {entry_date}

### English Learning
{english_summary}

### English Vocabulary
{english_vocab}

### Japanese News
{japanese_sections["news"]}

### Japanese Translation
{japanese_sections["translation"]}

### Japanese Vocabulary
{japanese_sections["vocabulary"]}

### Japanese Grammar
{japanese_sections["grammar"]}
""".strip()


def resolve_lark_token(config: Dict[str, str], timeout: int) -> str:
    token = (config.get("lark_access_token") or "").strip()
    if token:
        logging.info("Using existing Lark access token from configuration")
        return token
    app_id = config.get("lark_app_id")
    app_secret = config.get("lark_app_secret")
    if not app_id or not app_secret:
        raise ValueError(
            "Missing Lark credentials. Provide either lark_access_token or both "
            "lark_app_id and lark_app_secret in config.json."
        )
    return fetch_tenant_access_token(app_id, app_secret, timeout=timeout)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s"
    )
    project_root = Path(__file__).resolve().parent
    config = load_config(project_root / "config.json")
    timeout = config.get("request_timeout", 15)

    logging.info("Starting daily language learning task")

    hn_client = HackerNewsClient(timeout=timeout)
    english_items: List[HackerNewsStory] = hn_client.fetch_top_stories(
        desired=config.get("max_english_items", 4)
    )
    if not english_items:
        raise RuntimeError("Unable to fetch Hacker News stories.")
    english_prompt = hn_client.build_prompt(english_items)

    rss_client = JapaneseRSSClient(
        feed_url=config["japanese_rss_url"], timeout=timeout
    )
    japanese_items = rss_client.fetch_items(limit=config.get("max_japanese_items", 2))
    if not japanese_items:
        raise RuntimeError("Unable to fetch Japanese RSS news.")
    japanese_prompt = rss_client.build_prompt(japanese_items)

    llm_client = LLMClient(
        api_key=config["openai_api_key"],
        model=config.get("openai_model", "gpt-4o-mini"),
    )
    logging.info("Generating English learning content via OpenAI")
    english_data = generate_english_learning(llm_client, english_prompt)
    logging.info("Generating Japanese learning content via OpenAI")
    japanese_data = generate_japanese_learning(llm_client, japanese_prompt)

    english_summary, english_vocab = build_english_section(english_data)
    japanese_sections = build_japanese_section(japanese_items, japanese_data)

    today = datetime.now().strftime("%Y-%m-%d")
    new_entry = compose_markdown(today, english_summary, english_vocab, japanese_sections)

    month_title = datetime.now().strftime("Daily Language Learning %Y-%m")
    access_token = resolve_lark_token(config, timeout=timeout)
    lark_client = LarkClient(
        access_token=access_token,
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
