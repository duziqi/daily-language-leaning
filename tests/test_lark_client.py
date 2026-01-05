from lark_client import (
    MAX_DOC_TOKEN_LEN,
    _split_inline_code_spans,
    _extract_doc_token,
    _markdown_to_blocks,
    _normalize_doc_token,
)


def test_normalize_strips_docx_prefix_when_too_long():
    raw = "A" * MAX_DOC_TOKEN_LEN
    prefixed = f"docx{raw}"
    assert _normalize_doc_token(prefixed) == raw


def test_normalize_leaves_valid_token_untouched():
    raw = "B" * (MAX_DOC_TOKEN_LEN - 1)
    assert _normalize_doc_token(raw) == raw


def test_extract_doc_token_from_url_strips_prefix():
    raw = "C" * MAX_DOC_TOKEN_LEN
    url = f"https://example.com/docs/docx{raw}"
    assert _extract_doc_token(url) == raw


def test_markdown_to_blocks_preserves_headings_and_bullets():
    markdown = """## 2025-12-05
- item one
- item two

Plain text line"""
    blocks = _markdown_to_blocks(markdown)
    assert blocks[0]["block_type"] == "heading2"
    assert blocks[0]["text"] == "2025-12-05"
    assert blocks[1]["block_type"] == "bulleted"
    assert blocks[1]["text"] == "item one"
    assert blocks[2]["block_type"] == "bulleted"
    assert blocks[2]["text"] == "item two"
    assert blocks[3]["block_type"] == "paragraph"
    assert blocks[3]["text"] == "Plain text line"


def test_markdown_bullet_continuation_lines_merge():
    markdown = "- word\n  definition line\n  例句: sample"
    blocks = _markdown_to_blocks(markdown)
    assert len(blocks) == 1
    assert blocks[0]["block_type"] == "bulleted"
    assert "definition line" in blocks[0]["text"]
    assert "例句: sample" in blocks[0]["text"]


def test_markdown_to_blocks_supports_fenced_code_blocks():
    markdown = """Before

```text
line 1
line 2
```

After"""
    blocks = _markdown_to_blocks(markdown)
    assert blocks[0]["block_type"] == "paragraph"
    assert blocks[0]["text"] == "Before"
    assert blocks[1]["block_type"] == "code"
    assert blocks[1]["text"] == "line 1\nline 2"
    assert blocks[2]["block_type"] == "paragraph"
    assert blocks[2]["text"] == "After"


def test_split_inline_code_spans():
    spans = _split_inline_code_spans("a `b` c")
    assert spans == [("a ", False), ("b", True), (" c", False)]


def test_split_inline_code_spans_ignores_unclosed_backtick():
    spans = _split_inline_code_spans("a `b c")
    assert spans == [("a `b c", False)]
