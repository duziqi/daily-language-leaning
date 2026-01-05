from __future__ import annotations

from dataclasses import dataclass

from netflix_client import NetflixTechBlogRSSClient


@dataclass
class _FakeResponse:
    content: bytes

    def raise_for_status(self) -> None:
        return


class _FakeSession:
    def __init__(self, content: bytes):
        self._content = content
        self.calls = []

    def get(self, url: str, timeout: int = 10, verify=True):  # noqa: ANN001
        self.calls.append({"url": url, "timeout": timeout, "verify": verify})
        return _FakeResponse(content=self._content)


def test_netflix_rss_prefers_content_encoded_and_strips_html():
    rss = b"""<?xml version='1.0' encoding='UTF-8'?>
<rss version='2.0'
  xmlns:content='http://purl.org/rss/1.0/modules/content/'>
  <channel>
    <title>Netflix TechBlog</title>
    <item>
      <title>Example Post</title>
      <link>https://netflixtechblog.com/example</link>
      <pubDate>Mon, 05 Jan 2026 00:00:00 +0000</pubDate>
      <description><![CDATA[<p>Short desc</p>]]></description>
      <content:encoded><![CDATA[
        <h2>Heading</h2>
        <p>First paragraph.</p>
        <ul><li>Item A</li><li>Item B</li></ul>
      ]]></content:encoded>
    </item>
  </channel>
</rss>
"""
    session = _FakeSession(rss)
    client = NetflixTechBlogRSSClient(session=session, max_chars=0)
    items = client.fetch_latest(limit=1)
    assert len(items) == 1
    assert items[0].title == "Example Post"
    assert items[0].link == "https://netflixtechblog.com/example"
    assert "Heading" in items[0].content
    assert "First paragraph." in items[0].content
    assert "- Item A" in items[0].content
    assert "- Item B" in items[0].content
    assert "Short desc" not in items[0].content
    assert session.calls[0]["verify"] is True


def test_netflix_rss_truncates_when_max_chars_set():
    body = "<p>" + ("x" * 50) + "</p>"
    rss = f"""<?xml version='1.0' encoding='UTF-8'?>
<rss version='2.0' xmlns:content='http://purl.org/rss/1.0/modules/content/'>
  <channel>
    <item>
      <title>Example Post</title>
      <link>https://netflixtechblog.com/example</link>
      <content:encoded><![CDATA[{body}]]></content:encoded>
    </item>
  </channel>
</rss>
""".encode("utf-8")
    session = _FakeSession(rss)
    client = NetflixTechBlogRSSClient(session=session, max_chars=20)
    items = client.fetch_latest(limit=1)
    assert len(items) == 1
    assert items[0].content.endswith("...(truncated)")


def test_netflix_rss_ssl_fallback_retries_with_verify_false():
    rss = b"""<?xml version='1.0' encoding='UTF-8'?>
<rss version='2.0' xmlns:content='http://purl.org/rss/1.0/modules/content/'>
  <channel>
    <item>
      <title>Example Post</title>
      <link>https://netflixtechblog.com/example</link>
      <content:encoded><![CDATA[<p>Hello</p>]]></content:encoded>
    </item>
  </channel>
</rss>
"""

    class _SSLFailOnceSession(_FakeSession):
        def __init__(self, content: bytes):
            super().__init__(content)
            self._failed = False

        def get(self, url: str, timeout: int = 10, verify=True):  # noqa: ANN001
            from requests import exceptions as requests_exceptions

            self.calls.append({"url": url, "timeout": timeout, "verify": verify})
            if not self._failed:
                self._failed = True
                raise requests_exceptions.SSLError("bad cert")
            return _FakeResponse(content=self._content)

    session = _SSLFailOnceSession(rss)
    client = NetflixTechBlogRSSClient(
        session=session, allow_insecure_fallback=True, allow_curl_fallback=False
    )
    items = client.fetch_latest(limit=1)
    assert len(items) == 1
    assert session.calls[0]["verify"] is True
    assert session.calls[1]["verify"] is False
