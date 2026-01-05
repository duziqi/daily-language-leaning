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
  "english_rss_url": "https://feeds.arstechnica.com/arstechnica/index",
  "netflix_rss_url": "https://netflixtechblog.com/feed",
  "netflix_max_chars": 12000,
  "netflix_verify_ssl": true,
  "netflix_ca_bundle": "",
  "netflix_allow_insecure_fallback": false,
  "netflix_allow_curl_fallback": true,
  "japanese_rss_url": "https://www3.nhk.or.jp/rss/news/cat0.xml",
  "max_english_items": 4,
  "request_timeout": 15
}
```

- `openai_api_key`: standard OpenAI (or compatible) key.
- `openai_model`: override if you prefer another chat-completion model.
- `lark_app_id` & `lark_app_secret`: Feishu app credentials; the script will fetch a fresh tenant access token automatically for every run.
- `lark_access_token`: optional manual override; leave blank to auto-fetch via app credentials.
- `lark_folder_token`: Feishu Drive folder token where monthly Docs should be created (ensure it’s a Drive folder, not Knowledge Base).
- `english_rss_url`: Ars Technica RSS feed (default is the main site index); the script takes the 10 newest posts and filters AI/programming stories.
- `netflix_rss_url`: Netflix Tech Blog RSS feed used for the backend English-coaching section.
- `netflix_max_chars`: max characters of the Netflix article text to include in the LLM prompt (to avoid overly long inputs).
- `netflix_verify_ssl`: whether to verify HTTPS certificates when fetching the Netflix RSS feed (recommended: `true`).
- `netflix_ca_bundle`: optional path to a custom CA bundle file (PEM). Useful behind a corporate proxy.
- `netflix_allow_insecure_fallback`: if `true`, retry Netflix RSS fetch with `verify=false` when SSL verification fails (insecure; use only if you trust your network).
- `netflix_allow_curl_fallback`: if `true`, when SSL verification fails in Python, retry the RSS fetch via system `curl` (often uses macOS Keychain trust store).

If you see `SSLCertVerificationError` for Netflix while `curl` works, prefer setting `netflix_allow_curl_fallback` to `true` or configuring `netflix_ca_bundle`.
- `japanese_rss_url`: RSS feed that provides real Japanese news (default: NHK 国内総合 `cat0`).
- `request_timeout`: network timeout in seconds for all HTTP calls.

### Obtaining Feishu tokens

1. Create a Feishu app with `doc:read`, `doc:write`, `drive:read`, and `drive:write` scopes.
2. Record the app’s `app_id` and `app_secret`, and put them into `config.json`.
3. The script automatically calls `tenant_access_token/internal` each run; you do not need to refresh tokens manually. If you prefer to supply a token yourself, fill `lark_access_token` in your local `config.json`.
4. Grant the target Drive folder “edit” access to your app’s bot account (share the folder to the bot, or place the bot in a team space with access); otherwise the Drive API returns `forbidden`.
5. To get the folder token, open the folder in Feishu Drive and copy the token from the URL (`https://open.feishu.cn/open-apis/drive/home/?folder_token=fldxxxx`). The script will only reuse documents that are DocX type; if a legacy Doc already exists with the same name, it will create a new DocX file.

## Running the daily task

```bash
source .venv/bin/activate
python daily_task.py
```

What the script does:

1. Fetches the 10 latest Ars Technica posts, keeps the AI/programming-related ones, and builds an English-learning prompt (`ars_client.py`).
2. Fetches the latest Netflix Tech Blog article and extracts the full text for backend English coaching (`netflix_client.py`).
3. Fetches the latest five Japanese RSS articles from NHK (`rss_client.py`), randomly selects one for study, and includes both the original text and its romaji transcription.
4. Calls OpenAI to generate:
   - English tech news summary + Chinese translation
   - Backend architect English-coaching content (core tech chunks + logic connector + mock interview)
   - Japanese study notes with romaji-enhanced vocab lists (`llm_utils.py`).
5. Ensures a monthly Feishu Doc exists and prepends the new entry at the top (`lark_client.py`).

If you schedule it with cron, run the script from this repository root so `config.json` is found correctly.

## Troubleshooting

- Enable debug logs by setting `export PYTHONLOGGING=DEBUG` before running or edit `daily_task.py` to change the logging level.
- Verify Feishu tokens with a quick `curl` call if document creation fails.
- NHK feed occasionally omits descriptions; if random selection hits a blank item, rerun or adjust the `limit` parameter in `daily_task.py` to pull more than five candidates.
