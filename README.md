# Daily Language Learning

Automates a daily workflow that gathers real English technology news, real Japanese news, generates bilingual learning notes with OpenAI, and writes the result to a Feishu (Lark) Doc. Run `daily_task.py` once per day via cron, LaunchAgent, or any scheduler.

## Requirements

- Python 3.10+
- `requests` library (install via pip)
- Valid API credentials:
  - OpenAI (for `gpt-4o-mini` or any compatible chat-completion model)
  - Feishu (tenant access token with Doc permissions)

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

You can add additional libraries if you extend functionality; update `requirements.txt` accordingly.

## Configuration (`config.json`)

Copy the template and then edit your secrets:

```bash
cp config.example.json config.json
```

Fill in the fields:

```json
{
  "openai_api_key": "sk-xxx",
  "openai_model": "gpt-4o-mini",
  "lark_app_id": "cli_xxx",
  "lark_app_secret": "xxx",
  "lark_access_token": "",
  "lark_folder_token": "fldxxx",
  "japanese_rss_url": "https://www3.nhk.or.jp/news/easy/index.xml",
  "max_english_items": 4,
  "max_japanese_items": 2,
  "request_timeout": 15
}
```

- `openai_api_key`: standard OpenAI (or compatible) key.
- `openai_model`: override if you prefer another chat-completion model.
- `lark_app_id` & `lark_app_secret`: Feishu app credentials; the script will fetch a fresh tenant access token automatically for every run.
- `lark_access_token`: optional manual override; leave blank to auto-fetch via app credentials.
- `lark_folder_token`: Feishu Drive folder token where monthly Docs should be created (ensure it’s a Drive folder, not Knowledge Base).
- `japanese_rss_url`: RSS feed that provides real Japanese news (default: NHK News Web Easy).
- `request_timeout`: network timeout in seconds for all HTTP calls.

### Obtaining Feishu tokens

1. Create a Feishu app with `doc:read`, `doc:write`, `drive:read`, and `drive:write` scopes.
2. Record the app’s `app_id` and `app_secret`, and put them into `config.json`.
3. The script automatically calls `tenant_access_token/internal` each run; you do not need to refresh tokens manually. If you prefer to supply a token yourself, fill `lark_access_token` in your local `config.json`.
4. To get the folder token, open the folder in Feishu Drive and copy the token from the URL (`https://open.feishu.cn/open-apis/drive/home/?folder_token=fldxxxx`). The script will only reuse documents that are DocX type; if a legacy Doc already exists with the same name, it will create a new DocX file.

## Running the daily task

```bash
source .venv/bin/activate
python daily_task.py
```

What the script does:

1. Fetches 3–5 top Hacker News technology stories (`hn_client.py`).
2. Fetches 1–2 latest Japanese RSS articles (`rss_client.py`).
3. Calls OpenAI twice to generate English learning material and Japanese study notes (`llm_utils.py`).
4. Ensures a monthly Feishu Doc exists and prepends the new entry at the top (`lark_client.py`).

If you schedule it with cron, run the script from this repository root so `config.json` is found correctly.

## Troubleshooting

- Enable debug logs by setting `export PYTHONLOGGING=DEBUG` before running or edit `daily_task.py` to change the logging level.
- Verify Feishu tokens with a quick `curl` call if document creation fails.
- NHK feed occasionally omits descriptions; adjust `max_japanese_items` in `config.json` if you need more retries.
