from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import lark_oapi as lark
from lark_oapi.api.docx.v1 import (
    CreateDocumentBlockChildrenRequest,
    CreateDocumentBlockChildrenRequestBody,
    CreateDocumentRequest,
    CreateDocumentRequestBody,
)
from lark_oapi.api.docx.v1 import model as docx_models
from lark_oapi.api.drive.v1 import ListFileRequest
from lark_oapi.api.drive.v1 import model as drive_models

MAX_DOC_TOKEN_LEN = 27


def _normalize_doc_token(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    cleaned = token.strip().rstrip("/")
    cleaned = cleaned.split("?")[0]
    for prefix in ("docx", "doxc", "doc", "dox"):
        if cleaned.startswith(prefix) and len(cleaned) > MAX_DOC_TOKEN_LEN:
            cleaned = cleaned[len(prefix) :]
            break
    if len(cleaned) > MAX_DOC_TOKEN_LEN:
        logging.warning(
            "Document token '%s' exceeds %s characters after normalization.",
            cleaned,
            MAX_DOC_TOKEN_LEN,
        )
    return cleaned


def _extract_doc_token(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    token = url.rstrip("/").split("/")[-1]
    return _normalize_doc_token(token)


def _markdown_to_blocks(markdown: str) -> List[Dict[str, str]]:
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not normalized:
        return []
    lines = normalized.split("\n")
    blocks: List[Dict[str, str]] = []
    paragraph_buffer: List[str] = []
    current_bullet: Optional[Dict[str, str]] = None
    in_code_block = False
    code_buffer: List[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_buffer
        if paragraph_buffer:
            text = "\n".join(paragraph_buffer).strip()
            if text:
                blocks.append({"block_type": "paragraph", "text": text})
            paragraph_buffer = []

    def flush_bullet() -> None:
        nonlocal current_bullet
        if current_bullet:
            blocks.append(current_bullet)
            current_bullet = None

    def flush_code() -> None:
        nonlocal code_buffer
        if code_buffer:
            text = "\n".join(code_buffer).rstrip("\n")
            blocks.append({"block_type": "code", "text": text or " "})
            code_buffer = []

    for raw_line in lines:
        raw = raw_line.rstrip()
        stripped = raw.strip()
        if stripped.startswith("```"):
            if in_code_block:
                flush_code()
                in_code_block = False
            else:
                flush_paragraph()
                flush_bullet()
                in_code_block = True
                code_buffer = []
            continue
        if in_code_block:
            code_buffer.append(raw)
            continue
        if not stripped:
            flush_paragraph()
            flush_bullet()
            continue
        if stripped.startswith("#"):
            flush_paragraph()
            flush_bullet()
            level = len(stripped) - len(stripped.lstrip("#"))
            level = max(1, min(level, 6))
            content = stripped[level:].strip() or " "
            blocks.append({"block_type": f"heading{level}", "text": content})
            continue
        if stripped.startswith("- "):
            flush_paragraph()
            flush_bullet()
            text = stripped[2:].strip() or " "
            current_bullet = {"block_type": "bulleted", "text": text}
            continue
        if raw.startswith("  ") and current_bullet:
            addition = stripped or " "
            current_bullet["text"] = f"{current_bullet['text']}\n{addition}"
            continue
        if current_bullet:
            flush_bullet()
        paragraph_buffer.append(stripped or " ")

    flush_paragraph()
    flush_bullet()
    if in_code_block:
        flush_code()
    return blocks


def _split_inline_code_spans(text: str) -> List[Tuple[str, bool]]:
    if "`" not in text:
        return [(text, False)]
    if text.count("`") % 2 != 0:
        return [(text, False)]
    parts = text.split("`")
    spans: List[Tuple[str, bool]] = []
    for idx, part in enumerate(parts):
        if not part:
            continue
        spans.append((part, idx % 2 == 1))
    return spans or [(text, False)]


def _build_text(text: str) -> docx_models.Text:
    safe_text = text if text else " "
    elements: List[docx_models.TextElement] = []
    for segment, is_code in _split_inline_code_spans(safe_text):
        style = None
        if is_code:
            style = docx_models.TextElementStyle.builder().inline_code(True).build()
        text_run_builder = docx_models.TextRun.builder().content(segment)
        if style:
            text_run_builder.text_element_style(style)
        element = docx_models.TextElement.builder().text_run(text_run_builder.build()).build()
        elements.append(element)
    if not elements:
        elements.append(
            docx_models.TextElement.builder()
            .text_run(docx_models.TextRun.builder().content(" ").build())
            .build()
        )
    return docx_models.Text.builder().elements(elements).build()


def _build_block_object(spec: Dict[str, str]) -> docx_models.Block:
    block_type = spec.get("block_type", "paragraph")
    text_obj = _build_text(spec.get("text", ""))
    builder = docx_models.Block.builder()

    if block_type.startswith("heading"):
        try:
            level = int(block_type.replace("heading", ""))
        except ValueError:
            level = 1
        level = max(1, min(level, 6))
        builder.block_type(2 + level)
        heading_attr = f"heading{level}"
        getattr(builder, heading_attr)(text_obj)
    elif block_type == "bulleted":
        builder.block_type(12).bullet(text_obj)
    elif block_type == "code":
        builder.block_type(14).code(text_obj)
    else:
        builder.block_type(2).text(text_obj)

    return builder.build()


def _build_block_payload(markdown: str) -> List[docx_models.Block]:
    return [_build_block_object(spec) for spec in _markdown_to_blocks(markdown)]


class LarkClient:
    """Handles Feishu (Lark) Doc creation and prepending content via block APIs."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        root_folder_token: str,
        base_url: str = "https://open.feishu.cn",
        timeout: int = 10,
    ):
        builder = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .log_level(lark.LogLevel.ERROR)
        )
        builder.domain(base_url.rstrip("/"))
        builder.timeout(timeout)
        self.client = builder.build()
        self.root_folder_token = root_folder_token

    @staticmethod
    def _ensure_response(response, action: str) -> None:
        if response.success():
            return
        raw = ""
        if response.raw and response.raw.content:
            try:
                raw = response.raw.content.decode("utf-8")
            except Exception:
                raw = str(response.raw.content)
        logging.error(
            "Lark API %s failed (code=%s, msg=%s, log_id=%s, raw=%s)",
            action,
            response.code,
            response.msg,
            response.get_log_id(),
            raw[:500],
        )
        raise RuntimeError(f"Lark API {action} failed: {response.msg}")

    def list_documents(self, page_size: int = 50) -> List[drive_models.File]:
        request = (
            ListFileRequest.builder()
            .folder_token(self.root_folder_token)
            .page_size(page_size)
            .build()
        )
        response = self.client.drive.v1.file.list(request)
        self._ensure_response(response, "list files")
        if not response.data or not response.data.files:
            return []
        return response.data.files

    def find_document_by_title(self, title: str) -> Optional[str]:
        for item in self.list_documents():
            if item.name != title:
                continue
            if item.type != "docx":
                logging.warning(
                    "Found existing file named '%s' but type is %s; skipping",
                    title,
                    item.type,
                )
                continue
            doc_token = _normalize_doc_token(item.token) or _extract_doc_token(item.url)
            if not doc_token:
                logging.warning(
                    "Unable to determine doc token for '%s' from Drive metadata.", title
                )
                continue
            return doc_token
        return None

    def create_document(self, title: str) -> str:
        body = (
            CreateDocumentRequestBody.builder()
            .folder_token(self.root_folder_token)
            .title(title)
            .build()
        )
        request = CreateDocumentRequest.builder().request_body(body).build()
        response = self.client.docx.v1.document.create(request)
        self._ensure_response(response, "create document")
        doc = response.data.document if response.data else None
        token = _normalize_doc_token(doc.document_id) if doc else None
        if not token:
            raise RuntimeError("Failed to retrieve document token from creation response.")
        logging.info("Created new Lark document: %s", title)
        return token

    def ensure_document(self, title: str) -> str:
        token = self.find_document_by_title(title)
        if token:
            logging.info("Reusing existing Lark document: %s", title)
            return token
        return self.create_document(title)

    def prepend_content(self, document_token: str, new_markdown: str) -> None:
        token = _normalize_doc_token(document_token)
        if not token:
            raise ValueError("document_token is required to prepend content.")
        block_payload = _build_block_payload(new_markdown)
        if not block_payload:
            logging.info("No content provided to prepend.")
            return
        body = (
            CreateDocumentBlockChildrenRequestBody.builder()
            .children(block_payload)
            .index(0)
            .build()
        )
        request = (
            CreateDocumentBlockChildrenRequest.builder()
            .document_id(token)
            .block_id(token)
            .document_revision_id(-1)
            .request_body(body)
            .build()
        )
        response = self.client.docx.v1.document_block_children.create(request)
        self._ensure_response(response, "prepend blocks")
        logging.info("Prepended new content to document %s via block API", token)
