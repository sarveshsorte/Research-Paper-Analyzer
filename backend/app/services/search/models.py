import re
from dataclasses import dataclass, field


class SearchError(RuntimeError):
    """A search source failed; the message is safe to show in the trace."""


@dataclass
class PaperHit:
    source: str
    title: str
    pdf_url: str | None
    url: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None

    def keys(self) -> list[str]:
        """Every identifier this paper can be matched on: DOI, arXiv id, title."""
        keys = []
        if self.doi:
            keys.append("doi:" + self.doi.lower())
        if self.arxiv_id:
            keys.append("arxiv:" + re.sub(r"v\d+$", "", self.arxiv_id.lower()))
        keys.append("title:" + re.sub(r"[^a-z0-9]+", " ", self.title.lower()).strip())
        return keys

    def key(self) -> str:
        """The preferred identifier (DOI, then arXiv id, then title)."""
        return self.keys()[0]

    def authors_text(self) -> str | None:
        if not self.authors:
            return None
        names = ", ".join(self.authors[:3])
        return names + (" et al." if len(self.authors) > 3 else "")
