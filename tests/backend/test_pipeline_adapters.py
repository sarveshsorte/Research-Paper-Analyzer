"""The adapters run the teammates' pipelines unchanged (local embeddings, no LLM)."""

import asyncio
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from conftest import OTHER_PAPER_TEXT, PAPER_TEXT

from backend.app.adapters.document_pipeline import DocumentPipelineAdapter
from backend.app.adapters.providers import (
    WORKSPACE_ID,
    BM25SparseRetriever,
    HashingEmbedder,
)
from backend.app.adapters.query_pipeline import QueryPipelineAdapter
from backend.app.config import Settings
from backend.app.services.runtime import RuntimeStore
from backend.app.services.text import quote_in_text


class Steps:
    def __init__(self) -> None:
        self.steps: list[tuple[str, str, str | None]] = []

    def __call__(self, step_type: str, message: str, via: str | None = None) -> None:
        self.steps.append((step_type, message, via))

    def types(self) -> list[str]:
        return [step[0] for step in self.steps]


@pytest.fixture
def queries(
    store: RuntimeStore, settings: Settings, documents: DocumentPipelineAdapter
) -> QueryPipelineAdapter:
    return QueryPipelineAdapter(
        store,
        settings,
        HashingEmbedder(),
        BM25SparseRetriever(documents.bm25, store),
        None,
    )


def bm25_rows(path: str, document_id: str) -> int:
    with sqlite3.connect(path) as connection:
        return connection.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE workspace_id = ? AND paper_id = ?",
            (WORKSPACE_ID, document_id),
        ).fetchone()[0]


def test_processing_indexes_chunks_vectors_and_bm25(
    store: RuntimeStore,
    settings: Settings,
    add_ready_document: Callable[..., str],
) -> None:
    document_id = add_ready_document(None)

    document = store.get_document(document_id, None)
    assert document is not None
    assert (document["status"], document["pages"], document["chunks"]) == (
        "ready",
        1,
        1,
    )
    assert store.sections(document_id) == ["Introduction"]
    assert store.documents_with_vectors([document_id], "local-hashing-512") == {
        document_id
    }
    assert bm25_rows(settings.bm25_index_path, document_id) == 1


def test_a_pdf_title_from_its_metadata_is_used(
    store: RuntimeStore, documents: DocumentPipelineAdapter
) -> None:
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), PAPER_TEXT, fontsize=11)
    pdf.set_metadata({"title": "Adapters at Scale", "author": "A. Lovelace"})
    document = store.create_document("upload_2024.pdf", pdf.tobytes(), None)

    assert asyncio.run(documents.process(document["document_id"]))

    saved = store.get_document(document["document_id"], None)
    assert (saved["title"], saved["authors"]) == ("Adapters at Scale", "A. Lovelace")


def test_a_pdf_without_text_fails_with_a_short_message(
    store: RuntimeStore, documents: DocumentPipelineAdapter
) -> None:
    blank = pymupdf.open()
    blank.new_page()
    document = store.create_document("blank.pdf", blank.tobytes(), None)

    assert not asyncio.run(documents.process(document["document_id"]))

    saved = store.get_document(document["document_id"], None)
    assert saved["status"] == "failed"
    assert saved["error"].startswith("No text could be extracted")


def test_delete_index_removes_the_bm25_rows(
    settings: Settings,
    documents: DocumentPipelineAdapter,
    add_ready_document: Callable[..., str],
) -> None:
    document_id = add_ready_document(None)

    asyncio.run(documents.delete_index(document_id))

    assert bm25_rows(settings.bm25_index_path, document_id) == 0


def test_ask_quotes_the_papers_and_numbers_them(
    queries: QueryPipelineAdapter,
    store: RuntimeStore,
    add_ready_document: Callable[..., str],
) -> None:
    ids = [
        add_ready_document(None),
        add_ready_document(None, OTHER_PAPER_TEXT, "code-study.pdf"),
    ]
    steps = Steps()

    result = asyncio.run(
        queries.query("Do low-rank adapters match full fine-tuning?", ids, steps)
    )

    assert steps.types() == ["retrieving", "reranking", "reasoning", "validating"]
    assert result["claims"]
    for claim in result["claims"]:
        for evidence in claim["evidence"]:
            chunk = store.chunks_by_id([evidence["chunk_id"]])[evidence["chunk_id"]]
            assert quote_in_text(evidence["quote"], chunk.text)
            assert evidence["document_id"] in ids
    # [n] is the n-th paper of the request.
    assert "[1]" in result["answer"] or "[2]" in result["answer"]
    assert "[S" not in result["answer"]


def test_ask_says_when_the_papers_do_not_address_the_question(
    queries: QueryPipelineAdapter, add_ready_document: Callable[..., str]
) -> None:
    document_id = add_ready_document(None)

    result = asyncio.run(
        queries.query("What is the boiling point of mercury?", [document_id], Steps())
    )

    assert result["claims"] == []


def test_compare_fills_every_default_attribute_for_every_paper(
    queries: QueryPipelineAdapter, add_ready_document: Callable[..., str]
) -> None:
    ids = [
        add_ready_document(None),
        add_ready_document(None, OTHER_PAPER_TEXT, "code-study.pdf"),
    ]

    rows = asyncio.run(queries.compare(ids, [], Steps()))

    assert [row["attribute"] for row in rows] == [
        "Method",
        "Base model",
        "Benchmark",
        "Metric",
        "Headline result",
        "Code released",
    ]
    for row in rows:
        assert set(row["values"]) == set(ids)
        for cell in row["values"].values():
            assert cell["value"]


def test_conflicts_find_opposite_findings_with_verified_quotes(
    queries: QueryPipelineAdapter, add_ready_document: Callable[..., str]
) -> None:
    ids = [
        add_ready_document(None),
        add_ready_document(None, OTHER_PAPER_TEXT, "code-study.pdf"),
    ]

    conflicts = asyncio.run(queries.contradiction(ids, None, Steps()))

    assert conflicts
    first = conflicts[0]
    assert first["status"] in ("CONTRADICTED", "PARTIALLY_SUPPORTED")
    assert {first["claim_a"]["document_id"], first["claim_b"]["document_id"]} == set(
        ids
    )
    assert first["id"] == "C1"


def test_claim_judging_buckets_the_evidence(
    queries: QueryPipelineAdapter, add_ready_document: Callable[..., str]
) -> None:
    ids = [
        add_ready_document(None),
        add_ready_document(None, OTHER_PAPER_TEXT, "code-study.pdf"),
    ]
    steps = Steps()

    result: dict[str, Any] = asyncio.run(
        queries.judge_claim("Low-rank adapters match full fine-tuning", ids, steps)
    )

    assert result["supports"]
    assert result["contradicts"]
    assert result["verified_quotes"] == result["total_quotes"] > 0
    assert steps.types() == ["retrieving", "reasoning", "validating"]


def test_vectors_from_another_model_make_a_paper_not_ready(
    store: RuntimeStore,
    settings: Settings,
    documents: DocumentPipelineAdapter,
    add_ready_document: Callable[..., str],
) -> None:
    document_id = add_ready_document(None)
    other_model = QueryPipelineAdapter(
        store,
        settings,
        HashingEmbedder(256),
        BM25SparseRetriever(documents.bm25, store),
        None,
    )

    with pytest.raises(Exception, match="not indexed with the current embedding model"):
        asyncio.run(other_model.query("adapters", [document_id], Steps()))


def test_the_bm25_index_is_a_file_next_to_the_database(settings: Settings) -> None:
    assert Path(settings.bm25_index_path).parent == Path(settings.storage_path).parent
