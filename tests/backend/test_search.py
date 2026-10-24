"""Paper search and safe PDF downloads against mocked APIs (no network)."""

import asyncio
from collections.abc import Callable

import httpx
import pytest

from backend.app.services.search import (
    DownloadError,
    PdfDownloader,
    SearchError,
    SearchService,
)
from backend.app.services.search import download as download_module
from backend.app.services.search import service as service_module

ATOM_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2305.14314v1</id>
    <published>2023-05-23T17:50:33Z</published>
    <title>QLoRA: Efficient Finetuning of
      Quantized LLMs</title>
    <author><name>Tim Dettmers</name></author>
    <author><name>Artidoro Pagnoni</name></author>
  </entry>
</feed>"""

S2_REPLY = {
    "data": [
        {
            "title": "QLoRA: Efficient Finetuning of Quantized LLMs",
            "year": 2023,
            "authors": [{"name": "Tim Dettmers"}],
            "openAccessPdf": {"url": "https://arxiv.org/pdf/2305.14314"},
            "externalIds": {"ArXiv": "2305.14314", "DOI": "10.48550/arXiv.2305.14314"},
            "url": "https://www.semanticscholar.org/paper/abc",
        },
        {
            "title": "A paywalled paper",
            "year": 2020,
            "authors": [],
            "openAccessPdf": {"url": "https://publisher.example/paper.pdf"},
            "externalIds": {},
        },
    ]
}


@pytest.fixture(autouse=True)
def no_throttle_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_: float) -> None:
        return None

    monkeypatch.setattr(service_module.asyncio, "sleep", instant)


def service_for(
    handler: Callable[[httpx.Request], httpx.Response], tavily_key: str | None = None
) -> tuple[SearchService, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SearchService(client, PdfDownloader(client), tavily_key=tavily_key), client


def run(coroutine_factory, client: httpx.AsyncClient):
    async def main():
        async with client:
            return await coroutine_factory()

    return asyncio.run(main())


def test_semantic_scholar_and_arxiv_hits_merge_by_arxiv_id() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        if request.url.host == "api.semanticscholar.org":
            return httpx.Response(200, json=S2_REPLY)
        return httpx.Response(200, content=ATOM_FEED)

    service, client = service_for(handler)

    async def search():
        s2 = await service.search("semantic_scholar", ["quantized finetuning"], 5)
        arxiv = await service.search("arxiv", ["quantized finetuning"], 5)
        return s2, arxiv

    s2, arxiv = run(search, client)

    assert arxiv[0].title == "QLoRA: Efficient Finetuning of Quantized LLMs"
    assert (arxiv[0].arxiv_id, arxiv[0].year) == ("2305.14314v1", 2023)
    merged = service.merge(s2 + arxiv)
    # Same paper from both sources once; the paywalled host is dropped.
    assert [hit.title for hit in merged] == [
        "QLoRA: Efficient Finetuning of Quantized LLMs"
    ]
    assert merged[0].pdf_url == "https://arxiv.org/pdf/2305.14314"
    assert seen[0].params["openAccessPdf"] == ""
    assert "all:quantized AND all:finetuning" == seen[1].params["search_query"]


def test_a_rate_limited_source_reports_it() -> None:
    service, client = service_for(lambda request: httpx.Response(429))

    with pytest.raises(SearchError, match="rate limit"):
        run(lambda: service.semantic_scholar("claim", 5), client)


def test_tavily_needs_a_key_and_keeps_paper_links() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tvly-test"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "QLoRA", "url": "https://arxiv.org/abs/2305.14314"},
                    {"title": "Blog post", "url": "https://blog.example/qlora"},
                ]
            },
        )

    service, client = service_for(handler, tavily_key="tvly-test")
    hits = run(lambda: service.tavily("qlora", 5), client)

    assert [(h.title, h.pdf_url) for h in hits] == [
        ("QLoRA", "https://arxiv.org/pdf/2305.14314"),
        ("Blog post", None),
    ]
    assert not SearchService(client, PdfDownloader(client)).available("tavily")


@pytest.mark.parametrize(
    ("link", "pdf"),
    [
        ("https://arxiv.org/abs/2305.14314", "https://arxiv.org/pdf/2305.14314"),
        ("10.48550/arXiv.2305.14314", "https://arxiv.org/pdf/2305.14314"),
        ("https://openreview.net/pdf?id=abc", "https://openreview.net/pdf?id=abc"),
    ],
)
def test_resolve_link(link: str, pdf: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.semanticscholar.org":
            return httpx.Response(200, json=S2_REPLY["data"][0])
        return httpx.Response(200, content=ATOM_FEED)

    service, client = service_for(handler)

    assert run(lambda: service.resolve_link(link), client).pdf_url == pdf


def test_resolve_link_rejects_other_sites() -> None:
    service, client = service_for(lambda request: httpx.Response(404))

    with pytest.raises(SearchError, match="Enter an arXiv URL"):
        run(lambda: service.resolve_link("https://evil.example/file.pdf"), client)


def download(handler, url: str = "https://arxiv.org/pdf/1") -> tuple[bytes, str]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return run(lambda: PdfDownloader(client).download(url), client)


def test_download_follows_same_host_redirects_and_hashes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/pdf/1":
            return httpx.Response(302, headers={"location": "/pdf/1v2"})
        return httpx.Response(200, content=b"%PDF-1.7 body")

    content, sha256 = download(handler)

    assert content == b"%PDF-1.7 body"
    assert len(sha256) == 64


@pytest.mark.parametrize(
    ("handler", "url", "message"),
    [
        (
            lambda r: httpx.Response(200, content=b"%PDF"),
            "https://evil.example/a.pdf",
            "not on the list",
        ),
        (
            lambda r: httpx.Response(200, content=b"%PDF"),
            "http://openreview.net/a.pdf",
            "not on the list",
        ),
        (
            lambda r: httpx.Response(
                302, headers={"location": "https://evil.example/x"}
            ),
            "https://arxiv.org/pdf/1",
            "another site",
        ),
        (
            lambda r: httpx.Response(200, content=b"<html>login</html>"),
            "https://arxiv.org/pdf/1",
            "did not return a PDF",
        ),
        (lambda r: httpx.Response(404), "https://arxiv.org/pdf/1", "(404)"),
    ],
)
def test_download_refuses_unsafe_or_wrong_content(
    handler, url: str, message: str
) -> None:
    with pytest.raises(DownloadError, match=message):
        download(handler, url)


def test_download_stops_at_the_size_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(download_module, "MAX_PDF_BYTES", 10)

    with pytest.raises(DownloadError, match="over 25 MB"):
        download(lambda r: httpx.Response(200, content=b"%PDF-" + b"x" * 20))
