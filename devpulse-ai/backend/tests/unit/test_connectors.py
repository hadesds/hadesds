import json
from pathlib import Path

import httpx
import pytest

from devpulse import http as http_mod
from devpulse.content_extraction.extractor import parse_html
from devpulse.source_connectors.base import ConnectorContext, ConnectorError
from devpulse.source_connectors.mailbox import parse_rfc822
from devpulse.source_connectors.newsletter_parser import parse_newsletter
from devpulse.source_connectors.registry import available, get_connector

FIX = Path(__file__).parent.parent / "fixtures"


def client_for(body: bytes | str, status=200, ctype="application/rss+xml", headers=None):
    def handler(request):
        return httpx.Response(status, content=body if isinstance(body, bytes) else body.encode(), headers={"content-type": ctype, **(headers or {})})
    return http_mod.client(transport=httpx.MockTransport(handler))


def ctx(http, url="https://example.dev/feed", config=None, state=None):
    return ConnectorContext(http=http, source_config=config or {}, source_url=url, state=state or {}, since=None)


def test_registry_has_builtin_connectors():
    assert {"rss", "json_api", "github_releases", "webpage", "email_newsletter"} <= set(available())


def test_rss_items_have_url_and_original_date():
    res = get_connector("rss").fetch(ctx(client_for((FIX / "feed.xml").read_bytes())))
    assert len(res.items) == 1
    it = res.items[0]
    assert it.url.startswith("https://example.dev/blog/v5")
    assert it.published_at.isoformat() == "2026-10-26T12:00:00+00:00"
    assert it.external_id == "post-5"
    assert "Entrada sem link" in res.warnings[0]


def test_rss_handles_gzip_content_encoding():
    import gzip

    body = gzip.compress((FIX / "feed.xml").read_bytes())
    res = get_connector("rss").fetch(ctx(client_for(body, headers={"content-encoding": "gzip"})))
    assert len(res.items) == 1


def test_rss_http_error_raises():
    with pytest.raises(ConnectorError):
        get_connector("rss").fetch(ctx(client_for("x", status=500)))


def test_json_api_hackernews_preset():
    body = json.dumps({"hits": [
        {"objectID": "1", "title": "Show HN: thing", "url": "https://thing.dev", "created_at": "2026-10-27T10:00:00Z", "points": 150, "author": "a"},
        {"objectID": "2", "title": "Low points", "url": "https://low.dev", "created_at": "2026-10-27T10:00:00Z", "points": 3},
        {"objectID": "3", "title": "Ask HN: no url", "url": None, "created_at": "2026-10-27T10:00:00Z", "points": 200},
    ]})
    res = get_connector("json_api").fetch(ctx(client_for(body, ctype="application/json"), config={"preset": "hackernews", "min_points": 80}))
    urls = [i.url for i in res.items]
    assert urls == ["https://thing.dev", "https://news.ycombinator.com/item?id=3"]
    assert res.items[0].reference_type == "aggregator"


def test_json_api_cisa_preset():
    body = json.dumps({"vulnerabilities": [{"cveID": "CVE-2026-0001", "vendorProject": "Acme", "product": "Router",
                                             "vulnerabilityName": "Auth bypass", "shortDescription": "Bypass.", "dateAdded": "2099-01-01"}]})
    res = get_connector("json_api").fetch(ctx(client_for(body, ctype="application/json"), config={"preset": "cisa_kev"}))
    assert res.items[0].title == "Acme Router: Auth bypass (CVE-2026-0001)"
    assert res.items[0].url == "https://nvd.nist.gov/vuln/detail/CVE-2026-0001"
    assert res.items[0].category_hint == "seguranca"


def test_webpage_connector_filters_links():
    html = '<a href="/news/big-launch"><h3>A big launch for developers today</h3></a><a href="/news/announcements">Announcements</a><a href="/about">About</a>'
    res = get_connector("webpage").fetch(ctx(client_for(html, ctype="text/html"), url="https://site.dev/news",
                                             config={"link_pattern": "^/news/", "exclude_pattern": "announcements"}))
    assert [i.url for i in res.items] == ["https://site.dev/news/big-launch"]
    assert res.items[0].published_at is None  # nunca inventa data


def test_newsletter_parser_extracts_stories_and_skips_noise():
    stories = parse_newsletter((FIX / "newsletter.html").read_text())
    urls = [s.url for s in stories]
    assert "https://github.blog/news/agents?utm_campaign=x" in urls
    assert "https://blog.python.org/2026/10/python-3150a1/" in urls
    assert not any("instagram" in u or "unsubscribe" in u or "/view" in u for u in urls)
    assert all(len(s.context) <= 401 for s in stories)


def test_email_connector_requires_mailbox():
    with pytest.raises(ConnectorError, match="Nenhuma caixa"):
        get_connector("email_newsletter").fetch(ctx(client_for(""), config={"sender": "tech@newsletter.thedrops.com.br"}))


def test_parse_rfc822_multipart():
    raw = (
        b"From: TechDrops <tech@newsletter.thedrops.com.br>\r\nSubject: =?utf-8?q?Edi=C3=A7=C3=A3o?=\r\n"
        b"Date: Tue, 27 Oct 2026 08:00:00 -0300\r\nMessage-ID: <abc@x>\r\nMIME-Version: 1.0\r\n"
        b"Content-Type: multipart/alternative; boundary=b\r\n\r\n--b\r\nContent-Type: text/plain; charset=utf-8\r\n\r\ntexto\r\n"
        b"--b\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>html</p>\r\n--b--\r\n"
    )
    msg = parse_rfc822(raw)
    assert msg.subject == "Edição"
    assert msg.html.strip() == "<p>html</p>" and msg.text.strip() == "texto"
    assert msg.received_at.isoformat() == "2026-10-27T08:00:00-03:00"


def test_extractor_reads_metadata_and_paywall():
    html = """<html lang="en"><head><meta property="og:title" content="Big news">
    <meta property="article:published_time" content="2026-10-26T10:00:00Z"><meta property="og:image" content="/img.png">
    <script type="application/ld+json">{"@type":"NewsArticle","isAccessibleForFree":false,"author":{"name":"Ana"}}</script></head>
    <body><article><p>%s</p></article></body></html>""" % ("Long paragraph text. " * 20)
    page = parse_html("https://n.dev/a", "https://n.dev/a", 200, html)
    assert page.published_at.isoformat() == "2026-10-26T10:00:00+00:00"
    assert page.access == "restricted"
    assert page.images[0]["url"] == "https://n.dev/img.png"
    assert page.author == "Ana"
