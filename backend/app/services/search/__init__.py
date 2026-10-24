"""Paper search (Semantic Scholar, arXiv, Tavily) and safe open-access PDF downloads."""

from backend.app.services.search.download import DownloadError, PdfDownloader
from backend.app.services.search.models import PaperHit, SearchError
from backend.app.services.search.service import SearchService

__all__ = ["DownloadError", "PaperHit", "PdfDownloader", "SearchError", "SearchService"]
