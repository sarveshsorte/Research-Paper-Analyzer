"""Semantic Scholar, arXiv and Tavily search, and resolving pasted paper links.

Everything returned by these APIs is untrusted data: it is shown and stored,
never executed or used to build paths.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Sequence
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
from defusedxml import ElementTree

from backend.app.services.search.download import PdfDownloader
from backend.app.services.search.models import PaperHit, SearchError
from backend.app.services.text import content_terms

logger = logging.getLogger(__name__)

S2_API = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = "title,year,authors,openAccessPdf,externalIds,url"
ARXIV_API = "https://export.arxiv.org/api/query"
TAVILY_API = "https://api.tavily.com/search"
ATOM = "{http://www.w3.org/2005/Atom}"

# Tavily searches only paper sites, so its hits can become PDFs.
TAVILY_DOMAINS = [
    "arxiv.org",
    "aclanthology.org",
    "openreview.net",
    "proceedings.neurips.cc",
    "proceedings.mlr.press",
    "openaccess.thecvf.com",
    "pmc.ncbi.nlm.nih.gov",
    "biorxiv.org",
    "plos.org",
    "nature.com",
]

_ARXIV_ID = re.compile(
    r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v\d+)?|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})",
    re.I,
)
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.I)
_S2_PAPER = re.compile(r"semanticscholar\.org/paper/(?:[^/]+/)?([0-9a-f]{40})", re.I)

SOURCE_NAMES = {
    "semantic_scholar": "Semantic Scholar",
    "arxiv": "arXiv",
    "tavily": "Tavily",
}


class _Throttle:
    """At most one call per `interval` seconds (the APIs' published limits)."""

    def __init__(self, interval: float) -> None:
        self.interval = interval
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def __aenter__(self) -> None:
        await self._lock.acquire()
        wait = self._last + self.interval - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)

    async def __aexit__(self, *exc: object) -> None:
        self._last = time.monotonic()
        self._lock.release()


def _retry_after(response: httpx.Response, default: float = 3.0) -> float:
    value = response.headers.get("retry-after", "")
    return float(value) if value.isdigit() and int(value) <= 10 else default


def arxiv_pdf(arxiv_id: str) -> str:
    return f"https://arxiv.org/pdf/{arxiv_id}"


class SearchService:
    def __init__(
        self,
        client: httpx.AsyncClient,
        downloader: PdfDownloader,
        *,
        semantic_scholar_key: str | None = None,
        tavily_key: str | None = None,
    ) -> None:
        self.client = client
        self.downloader = downloader
        self.semantic_scholar_key = semantic_scholar_key
        self.tavily_key = tavily_key
        self._s2_throttle = _Throttle(1.1)
        self._arxiv_throttle = _Throttle(3.0)

    async def _get(
        self,
        throttle: _Throttle,
        name: str,
        url: str,
        *,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
        timeout: float = 20,
    ) -> httpx.Response:
        """GET within the source's rate limit, retrying once after a 429."""
        for attempt in range(2):
            async with throttle:
                try:
                    response = await self.client.get(
                        url, params=params, headers=headers or {}, timeout=timeout
                    )
                except httpx.HTTPError as exc:
                    raise SearchError(f"{name} could not be reached.") from exc
            if response.status_code != 429 or attempt == 1:
                return response
            await asyncio.sleep(_retry_after(response))
        return response

    def available(self, source: str) -> bool:
        return source != "tavily" or bool(self.tavily_key)

    async def search(
        self, source: str, queries: Sequence[str], limit: int
    ) -> list[PaperHit]:
        if source == "semantic_scholar":
            run = self.semantic_scholar
        elif source == "arxiv":
            run = self.arxiv
        elif source == "tavily":
            run = self.tavily
        else:
            raise SearchError(f"Unknown source {source}.")
        hits: list[PaperHit] = []
        for query in queries:
            hits.extend(await run(query, limit))
        return hits

    # Semantic Scholar

    def _s2_headers(self) -> dict[str, str]:
        return (
            {"x-api-key": self.semantic_scholar_key}
            if self.semantic_scholar_key
            else {}
        )

    @staticmethod
    def _s2_hit(paper: dict[str, Any]) -> PaperHit | None:
        title = paper.get("title")
        if not isinstance(title, str) or not title.strip():
            return None
        ids = paper.get("externalIds") or {}
        pdf = (paper.get("openAccessPdf") or {}).get("url") or None
        arxiv_id = ids.get("ArXiv")
        if arxiv_id and not pdf:
            pdf = arxiv_pdf(arxiv_id)
        authors = [a.get("name") for a in paper.get("authors") or [] if a.get("name")]
        year = paper.get("year")
        return PaperHit(
            source="semantic_scholar",
            title=" ".join(title.split()),
            pdf_url=pdf,
            url=paper.get("url"),
            doi=ids.get("DOI"),
            arxiv_id=arxiv_id,
            authors=authors,
            year=year if isinstance(year, int) else None,
        )

    async def semantic_scholar(self, query: str, limit: int) -> list[PaperHit]:
        response = await self._get(
            self._s2_throttle,
            "Semantic Scholar",
            f"{S2_API}/paper/search",
            params={
                "query": query[:300],
                "limit": min(limit, 50),
                "fields": S2_FIELDS,
                "openAccessPdf": "",
            },
            headers=self._s2_headers(),
        )
        if response.status_code == 429:
            raise SearchError("Semantic Scholar rate limit reached (429).")
        if response.status_code != 200:
            raise SearchError(f"Semantic Scholar returned {response.status_code}.")
        papers = response.json().get("data") or []
        return [hit for paper in papers if (hit := self._s2_hit(paper))]

    async def semantic_scholar_paper(self, paper_id: str) -> PaperHit | None:
        response = await self._get(
            self._s2_throttle,
            "Semantic Scholar",
            f"{S2_API}/paper/{quote(paper_id, safe=':/.')}",
            params={"fields": S2_FIELDS},
            headers=self._s2_headers(),
        )
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise SearchError(f"Semantic Scholar returned {response.status_code}.")
        return self._s2_hit(response.json())

    # arXiv

    @staticmethod
    def _arxiv_query(text: str) -> str:
        terms = list(dict.fromkeys(content_terms(text)))[:5]
        if not terms:
            return f'all:"{text[:100]}"'
        return " AND ".join(f"all:{term}" for term in terms)

    async def _arxiv_call(self, params: dict[str, Any]) -> list[PaperHit]:
        response = await self._get(
            self._arxiv_throttle, "arXiv", ARXIV_API, params=params, timeout=25
        )
        if response.status_code == 429:
            raise SearchError("arXiv rate limit reached (429).")
        if response.status_code != 200:
            raise SearchError(f"arXiv returned {response.status_code}.")
        try:
            root = ElementTree.fromstring(response.content)
        except Exception as exc:
            raise SearchError("arXiv returned an unreadable reply.") from exc
        hits = []
        for entry in root.findall(f"{ATOM}entry"):
            title = " ".join((entry.findtext(f"{ATOM}title") or "").split())
            abs_url = entry.findtext(f"{ATOM}id") or ""
            match = _ARXIV_ID.search(abs_url)
            if not title or not match:
                continue
            published = entry.findtext(f"{ATOM}published") or ""
            hits.append(
                PaperHit(
                    source="arxiv",
                    title=title,
                    pdf_url=arxiv_pdf(match.group(1)),
                    url=abs_url,
                    arxiv_id=match.group(1),
                    authors=[
                        " ".join((a.findtext(f"{ATOM}name") or "").split())
                        for a in entry.findall(f"{ATOM}author")
                    ],
                    year=int(published[:4]) if published[:4].isdigit() else None,
                )
            )
        return hits

    async def arxiv(self, query: str, limit: int) -> list[PaperHit]:
        hits = await self._arxiv_call(
            {
                "search_query": self._arxiv_query(query),
                "start": 0,
                "max_results": min(limit, 30),
                "sortBy": "relevance",
            }
        )
        if not hits:
            terms = list(dict.fromkeys(content_terms(query)))[:2]
            if len(terms) == 2:
                hits = await self._arxiv_call(
                    {
                        "search_query": " AND ".join(f"all:{t}" for t in terms),
                        "start": 0,
                        "max_results": min(limit, 30),
                        "sortBy": "relevance",
                    }
                )
        return hits

    async def arxiv_paper(self, arxiv_id: str) -> PaperHit | None:
        hits = await self._arxiv_call({"id_list": arxiv_id, "max_results": 1})
        return hits[0] if hits else None

    # Tavily

    async def tavily(self, query: str, limit: int) -> list[PaperHit]:
        if not self.tavily_key:
            raise SearchError("Tavily is not configured (TAVILY_API_KEY).")
        try:
            response = await self.client.post(
                TAVILY_API,
                headers={"Authorization": f"Bearer {self.tavily_key}"},
                json={
                    "query": query[:400],
                    "search_depth": "basic",
                    "max_results": min(limit, 20),
                    "include_domains": TAVILY_DOMAINS,
                },
                timeout=25,
            )
        except httpx.HTTPError as exc:
            raise SearchError("Tavily could not be reached.") from exc
        if response.status_code != 200:
            raise SearchError(f"Tavily returned {response.status_code}.")
        hits = []
        for result in response.json().get("results") or []:
            url = result.get("url") or ""
            title = " ".join(str(result.get("title") or "").split())
            if not url or not title:
                continue
            arxiv = _ARXIV_ID.search(url)
            if arxiv:
                pdf = arxiv_pdf(arxiv.group(1))
            elif urlsplit(url).path.lower().endswith(".pdf"):
                pdf = url
            else:
                pdf = None
            hits.append(
                PaperHit(
                    source="tavily",
                    title=title,
                    pdf_url=pdf,
                    url=url,
                    arxiv_id=arxiv.group(1) if arxiv else None,
                )
            )
        return hits

    # Merge

    def merge(self, hits: Sequence[PaperHit]) -> list[PaperHit]:
        """Deduplicated by DOI, arXiv id, then title; downloadable PDFs only."""
        by_key: dict[str, PaperHit] = {}
        merged: list[PaperHit] = []
        for hit in hits:
            existing = next((by_key[k] for k in hit.keys() if k in by_key), None)
            if existing is None:
                merged.append(hit)
                existing = hit
            else:
                # Keep the first hit, filling what it lacks.
                if not self.downloader.is_allowed(existing.pdf_url) and hit.pdf_url:
                    existing.pdf_url = hit.pdf_url
                existing.authors = existing.authors or hit.authors
                existing.year = existing.year or hit.year
                existing.doi = existing.doi or hit.doi
                existing.arxiv_id = existing.arxiv_id or hit.arxiv_id
            for key in [*hit.keys(), *existing.keys()]:
                by_key.setdefault(key, existing)
        return [hit for hit in merged if self.downloader.is_allowed(hit.pdf_url)]

    # Fetch by link

    async def resolve_link(self, text: str) -> PaperHit:
        """An arXiv URL, a DOI, a Semantic Scholar paper link or a direct PDF link."""
        text = text.strip()
        arxiv = _ARXIV_ID.search(text)
        if arxiv:
            arxiv_id = arxiv.group(1)
            hit = None
            try:
                hit = await self.arxiv_paper(arxiv_id)
            except SearchError:
                logger.warning("arxiv_lookup_failed id=%s", arxiv_id)
            if hit is None:
                return PaperHit(
                    source="link",
                    title=f"arXiv {arxiv_id}",
                    pdf_url=arxiv_pdf(arxiv_id),
                    url=text,
                    arxiv_id=arxiv_id,
                )
            # The version the link asked for (latest when it names none).
            hit.pdf_url, hit.arxiv_id = arxiv_pdf(arxiv_id), arxiv_id
            return hit
        s2 = _S2_PAPER.search(text)
        doi = None if s2 else _DOI.search(text)
        if s2 or doi:
            paper_id = s2.group(1) if s2 else f"DOI:{doi.group(1).rstrip('.')}"
            hit = await self.semantic_scholar_paper(paper_id)
            if hit is None:
                raise SearchError("Semantic Scholar has no paper for that link.")
            if not self.downloader.is_allowed(hit.pdf_url):
                raise SearchError("No open-access PDF is available for that paper.")
            return hit
        if self.downloader.is_allowed(text):
            name = urlsplit(text).path.rsplit("/", 1)[-1] or "paper.pdf"
            return PaperHit(source="link", title=name, pdf_url=text, url=text)
        raise SearchError(
            "Enter an arXiv URL, DOI or Semantic Scholar link, or a PDF link from a "
            "supported open-access site."
        )
