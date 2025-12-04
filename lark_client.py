from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests


def _extract_doc_token(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    token = url.rstrip("/").split("/")[-1]
    if not token:
        return None
    # Ensure doc/docx prefix present; some URLs already include it.
    if token.startswith(("docx", "doc", "doxc", "dox")):
        return token
    # Some APIs return bare token without prefix; add docx prefix.
    return f"docx{token}"


class LarkClient:
    """Handles Feishu (Lark) Doc creation and prepending content."""

    def __init__(
        self,
        access_token: str,
        root_folder_token: str,
        base_url: str = "https://open.feishu.cn",
        timeout: int = 10,
    ):
        self.access_token = access_token
        self.root_folder_token = root_folder_token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = requests.request(method, url, headers=self.headers, timeout=self.timeout, **kwargs)
        if resp.status_code >= 400:
            logging.error("Lark API error %s for %s %s: %s", resp.status_code, method, path, resp.text[:500])
            resp.raise_for_status()
        data = resp.json()
        if data.get("code", 0) != 0 and "data" in data:
            logging.error("Lark API non-zero code for %s: %s", path, data)
            raise RuntimeError(f"Lark API error: {data}")
        return data

    def list_documents(self, page_size: int = 50) -> Dict[str, Any]:
        params = {"folder_token": self.root_folder_token, "page_size": page_size}
        return self._request("GET", "/open-apis/drive/v1/files", params=params)

    def find_document_by_title(self, title: str) -> Optional[str]:
        response = self.list_documents()
        for item in response.get("data", {}).get("files", []):
            if item.get("name") != title:
                continue
            if item.get("type") != "docx":
                logging.warning(
                    "Found existing file named '%s' but type is %s; skipping",
                    title,
                    item.get("type"),
                )
                continue
            doc_token = item.get("document_id") or _extract_doc_token(item.get("url"))
            if not doc_token:
                logging.warning(
                    "Unable to determine doc token for '%s' from Drive metadata.", title
                )
                continue
            return doc_token
        return None

    def create_document(self, title: str) -> str:
        payload = {"title": title, "folder_token": self.root_folder_token}
        data = self._request("POST", "/open-apis/docx/v1/documents", json=payload)
        doc = data.get("data", {}).get("document", {})
        token = doc.get("document_id") or _extract_doc_token(doc.get("url"))
        if not token:
            raise RuntimeError("Failed to retrieve document token from creation response.")
        logging.info("Created new Lark document: %s", title)
        return token

    def get_raw_content(self, document_token: str) -> str:
        data = self._request(
            "GET", f"/open-apis/docx/v1/documents/{document_token}/raw_content"
        )
        return data.get("data", {}).get("content", "")

    def update_raw_content(self, document_token: str, content: str) -> None:
        payload = {"content": content}
        self._request(
            "PATCH", f"/open-apis/docx/v1/documents/{document_token}/raw_content", json=payload
        )

    def ensure_document(self, title: str) -> str:
        token = self.find_document_by_title(title)
        if token:
            logging.info("Reusing existing Lark document: %s", title)
            return token
        return self.create_document(title)

    def prepend_content(self, document_token: str, new_markdown: str) -> None:
        current = self.get_raw_content(document_token)
        new_content = f"{new_markdown.strip()}\n\n{current}".strip()
        self.update_raw_content(document_token, new_content)
        logging.info("Prepended new content to document %s", document_token)


def fetch_tenant_access_token(
    app_id: str,
    app_secret: str,
    base_url: str = "https://open.feishu.cn",
    timeout: int = 10,
) -> str:
    """Request a fresh tenant access token using app credentials."""
    url = f"{base_url.rstrip('/')}/open-apis/auth/v3/tenant_access_token/internal"
    payload = {"app_id": app_id, "app_secret": app_secret}
    logging.info("Requesting new Lark tenant access token")
    resp = requests.post(url, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        logging.error("Failed to retrieve Lark tenant token: %s", resp.text[:500])
        resp.raise_for_status()
    data = resp.json()
    if data.get("code", 0) != 0:
        raise RuntimeError(f"Lark auth error: {data}")
    token = data.get("tenant_access_token")
    if not token:
        raise RuntimeError("Lark response missing tenant_access_token")
    return token
