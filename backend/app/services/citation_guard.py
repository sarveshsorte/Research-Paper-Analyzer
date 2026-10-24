"""Citation guard: every quote shown to a user must be in its chunk's stored text."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from backend.app.services.runtime import StoredChunk
from backend.app.services.text import quote_in_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GuardResult:
    kept: list[dict[str, Any]]
    checked: int
    verified: int


def guard_evidence(
    evidence: list[dict[str, Any]], chunks: Mapping[str, StoredChunk]
) -> GuardResult:
    """Keeps evidence whose `quote` is in the text of its `chunk_id`.

    The chunk must also belong to the evidence's `document_id` and its page
    range must include `page`. Failures are dropped and logged.
    """
    kept = []
    for item in evidence:
        chunk = chunks.get(item.get("chunk_id", ""))
        page = item.get("page")
        if (
            chunk is not None
            and chunk.document_id == item.get("document_id")
            and isinstance(page, int)
            and chunk.page_start <= page <= chunk.page_end
            and quote_in_text(str(item.get("quote", "")), chunk.text)
        ):
            kept.append(item)
        else:
            logger.warning(
                "citation_guard_dropped chunk_id=%s document_id=%s page=%s",
                item.get("chunk_id"),
                item.get("document_id"),
                page,
            )
    return GuardResult(kept=kept, checked=len(evidence), verified=len(kept))
