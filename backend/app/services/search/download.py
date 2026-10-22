"""Safe open-access PDF downloads.

Only HTTPS URLs on allowlisted hosts; redirects must stay on the same host;
a 25 MB cap and a 30 s timeout; the body must start with %PDF-.
"""

from __future__ import annotations

import hashlib
from urllib.parse import urljoin, urlsplit

import httpx

MAX_PDF_BYTES = 25 * 1024 * 1024
TIMEOUT_SECONDS = 30
MAX_REDIRECTS = 3

# Open-access paper hosts. Extend with DOWNLOAD_ALLOWED_HOSTS.
ALLOWED_HOSTS = frozenset(
    {
        "arxiv.org",
        "export.arxiv.org",
        "www.arxiv.org",
        "aclanthology.org",
        "openreview.net",
        "proceedings.neurips.cc",
        "papers.nips.cc",
        "proceedings.mlr.press",
        "jmlr.org",
        "www.jmlr.org",
        "openaccess.thecvf.com",
        "ojs.aaai.org",
        "www.ijcai.org",
        "pdfs.semanticscholar.org",
        "www.semanticscholar.org",
        "europepmc.org",
        "pmc.ncbi.nlm.nih.gov",
        "www.ncbi.nlm.nih.gov",
        "www.biorxiv.org",
        "www.medrxiv.org",
        "journals.plos.org",
        "peerj.com",
        "elifesciences.org",
        "www.mdpi.com",
        "www.frontiersin.org",
        "www.nature.com",
        "link.springer.com",
        "dl.acm.org",
        "zenodo.org",
    }
)


class DownloadError(RuntimeError):
    """The PDF could not be downloaded; the message is safe to show."""


class PdfDownloader:
    def __init__(self, client: httpx.AsyncClient, extra_hosts: str = "") -> None:
        self.client = client
        extra = {h.strip().lower() for h in extra_hosts.split(",") if h.strip()}
        self.allowed_hosts = ALLOWED_HOSTS | extra

    def normalize(self, url: str) -> str | None:
        """An https URL on an allowed host, or None. arXiv http links are upgraded."""
        try:
            parts = urlsplit(url.strip())
        except ValueError:
            return None
        host = (parts.hostname or "").lower()
        if host not in self.allowed_hosts or parts.username or parts.password:
            return None
        if parts.port not in (None, 443):
            return None
        if parts.scheme == "http" and host.endswith("arxiv.org"):
            parts = parts._replace(scheme="https")
        if parts.scheme != "https":
            return None
        return parts.geturl()

    def is_allowed(self, url: str | None) -> bool:
        return bool(url) and self.normalize(url) is not None

    async def download(self, url: str) -> tuple[bytes, str]:
        """(PDF bytes, sha256 hex)."""
        current = self.normalize(url)
        if current is None:
            raise DownloadError(
                "That site is not on the list of open-access PDF hosts."
            )
        host = urlsplit(current).hostname
        for _ in range(MAX_REDIRECTS + 1):
            try:
                async with self.client.stream(
                    "GET",
                    current,
                    follow_redirects=False,
                    timeout=TIMEOUT_SECONDS,
                    headers={"Accept": "application/pdf"},
                ) as response:
                    if response.is_redirect:
                        target = urljoin(current, response.headers.get("location", ""))
                        target = self.normalize(target) or ""
                        if urlsplit(target).hostname != host:
                            raise DownloadError(
                                "The PDF link redirects to another site."
                            )
                        current = target
                        continue
                    if response.status_code != 200:
                        raise DownloadError(
                            f"The PDF host returned an error ({response.status_code})."
                        )
                    return await self._read(response)
            except httpx.HTTPError as exc:
                raise DownloadError("The PDF could not be downloaded.") from exc
        raise DownloadError("The PDF link redirects too many times.")

    @staticmethod
    async def _read(response: httpx.Response) -> tuple[bytes, str]:
        length = response.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_PDF_BYTES:
            raise DownloadError("The PDF is over 25 MB.")
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_PDF_BYTES:
                raise DownloadError("The PDF is over 25 MB.")
            digest.update(chunk)
            chunks.append(chunk)
        content = b"".join(chunks)
        if not content.startswith(b"%PDF-"):
            raise DownloadError("The link did not return a PDF.")
        return content, digest.hexdigest()
