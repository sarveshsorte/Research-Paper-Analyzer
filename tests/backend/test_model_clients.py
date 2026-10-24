"""Nemotron (Nebius Token Factory) and embedding clients against a mocked HTTP API."""

import asyncio
import json
import re
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from conftest import OTHER_PAPER_TEXT

from backend.app.adapters import providers
from backend.app.adapters.document_pipeline import DocumentPipelineAdapter
from backend.app.adapters.providers import (
    BM25SparseRetriever,
    ChatModel,
    HashingEmbedder,
    RemoteEmbedder,
    UpstreamError,
    parse_json_object,
)
from backend.app.adapters.query_pipeline import QueryPipelineAdapter
from backend.app.config import Settings
from backend.app.services.runtime import RuntimeStore
from backend.app.services.text import quote_in_text

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_: float) -> None:
        return None

    monkeypatch.setattr(providers.asyncio, "sleep", instant)


def client_for(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def chat_reply(content: dict[str, Any] | str) -> httpx.Response:
    text = content if isinstance(content, str) else json.dumps(content)
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


def passages(request: httpx.Request) -> dict[str, str]:
    """source id → passage text, from the prompt the backend sent."""
    user = json.loads(request.content)["messages"][1]["content"]
    return dict(
        re.findall(r'<passage id="(S\d+)"[^>]*>\n(.*?)\n</passage>', user, re.S)
    )


def test_parse_json_object_ignores_reasoning_and_fences() -> None:
    raw = '<think>plan the answer</think>\n```json\n{"answer": "Yes [S1]"}\n```'

    assert parse_json_object(raw) == {"answer": "Yes [S1]"}


def test_chat_retries_without_json_mode_when_rejected() -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": "response_format unsupported"})
        return chat_reply({"ok": True})

    async def run() -> dict[str, Any]:
        async with client_for(handler) as client:
            chat = ChatModel(
                client, base_url="https://nebius.test/v1/", api_key="k", model="m"
            )
            return await chat.complete_json("system", "user")

    assert asyncio.run(run()) == {"ok": True}
    assert ["response_format" in call for call in calls] == [True, False]
    assert calls[0]["model"] == "m"


def test_chat_does_not_hide_an_auth_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    async def run() -> None:
        async with client_for(handler) as client:
            chat = ChatModel(
                client, base_url="https://nebius.test/v1", api_key="k", model="m"
            )
            await chat.complete_json("system", "user")

    with pytest.raises(UpstreamError, match=r"\(401\)"):
        asyncio.run(run())


def test_nvidia_embeddings_send_input_type_and_retry_server_errors() -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(503)
        assert request.headers["Authorization"] == "Bearer nv-key"
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    async def run() -> list[float]:
        async with client_for(handler) as client:
            embedder = RemoteEmbedder(
                client,
                base_url="https://integrate.api.nvidia.com/v1",
                api_key="nv-key",
                model="nvidia/embed",
                dimension=3,
                input_type="query",
            )
            return await embedder.embed("adapters")

    assert asyncio.run(run()) == [0.1, 0.2, 0.3]
    assert calls[-1] == {
        "model": "nvidia/embed",
        "input": ["adapters"],
        "encoding_format": "float",
        "input_type": "query",
        "truncate": "END",
    }


@pytest.fixture
def two_papers(add_ready_document: Callable[..., str]) -> list[str]:
    return [
        add_ready_document(None),
        add_ready_document(None, OTHER_PAPER_TEXT, "code-study.pdf"),
    ]


def adapter_with(
    handler: Handler,
    store: RuntimeStore,
    settings: Settings,
    documents: DocumentPipelineAdapter,
) -> tuple[QueryPipelineAdapter, httpx.AsyncClient]:
    client = client_for(handler)
    chat = ChatModel(
        client,
        base_url="https://nebius.test/v1",
        api_key="k",
        model="nvidia/nemotron-test",
    )
    adapter = QueryPipelineAdapter(
        store,
        settings,
        HashingEmbedder(),
        BM25SparseRetriever(documents.bm25, store),
        chat,
    )
    return adapter, client


def test_ask_with_nemotron_keeps_real_quotes_and_replaces_invented_ones(
    store: RuntimeStore,
    settings: Settings,
    documents: DocumentPipelineAdapter,
    two_papers: list[str],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        found = passages(request)
        source = next(sid for sid, text in found.items() if "math reasoning" in text)
        return chat_reply(
            {
                "answer": f"Adapters match full fine-tuning on math [{source}].",
                "claims": [
                    {
                        "text": "Adapters match full fine-tuning on math reasoning.",
                        "source_ids": [source],
                        "quotes": {
                            source: "Low-rank adapters match full fine-tuning on "
                            "math reasoning benchmarks."
                        },
                        "confidence": 0.9,
                    },
                    {
                        "text": "Adapters train faster.",
                        "source_ids": [source],
                        "quotes": {source: "Adapters are always faster than anything."},
                        "confidence": 0.8,
                    },
                    {"text": "Unsourced claim.", "source_ids": ["S99"], "quotes": {}},
                ],
                "uncertainties": [],
            }
        )

    adapter, client = adapter_with(handler, store, settings, documents)

    async def run() -> dict[str, Any]:
        async with client:
            return await adapter.query(
                "Do adapters match full fine-tuning on math?",
                two_papers,
                lambda *a: None,
            )

    result = asyncio.run(run())

    assert result["answer"] == "Adapters match full fine-tuning on math [1]."
    assert [c["claim"] for c in result["claims"]] == [
        "Adapters match full fine-tuning on math reasoning.",
        "Adapters train faster.",
    ]
    assert result["claims"][0]["confidence"] == 0.9
    first_quote = result["claims"][0]["evidence"][0]["quote"]
    assert (
        first_quote
        == "Low-rank adapters match full fine-tuning on math reasoning benchmarks."
    )
    invented = result["claims"][1]["evidence"][0]
    chunk = store.chunks_by_id([invented["chunk_id"]])[invented["chunk_id"]]
    assert invented["quote"] != "Adapters are always faster than anything."
    assert quote_in_text(invented["quote"], chunk.text)


def test_compare_and_judge_with_nemotron(
    store: RuntimeStore,
    settings: Settings,
    documents: DocumentPipelineAdapter,
    two_papers: list[str],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        found = passages(request)
        system = json.loads(request.content)["messages"][0]["content"]
        if "attribute by attribute" in system:
            p1 = next(sid for sid, text in found.items() if "math reasoning" in text)
            return chat_reply(
                {
                    "values": {
                        "P1": {"value": "Low-rank adapters", "source_id": p1},
                        "P2": {"value": "Invented without a source", "source_id": None},
                    }
                }
            )
        support = next(sid for sid, text in found.items() if "math reasoning" in text)
        against = next(sid for sid, text in found.items() if "code generation" in text)
        return chat_reply(
            {
                "judgements": [
                    {
                        "source_id": support,
                        "verdict": "supports",
                        "quote": "Low-rank adapters match full fine-tuning on "
                        "math reasoning "
                        "benchmarks.",
                        "note": "",
                    },
                    {
                        "source_id": against,
                        "verdict": "contradicts",
                        "quote": "Low-rank adapters do not match full fine-tuning "
                        "on code "
                        "generation benchmarks.",
                        "note": "",
                    },
                ],
                "summary": "The evidence is mixed: it holds for math, not for code.",
                "summary_highlight": "mixed",
            }
        )

    adapter, client = adapter_with(handler, store, settings, documents)

    async def run() -> tuple[list[dict[str, Any]], dict[str, Any]]:
        async with client:
            rows = await adapter.compare(two_papers, ["Method"], lambda *a: None)
            judged = await adapter.judge_claim(
                "Low-rank adapters match full fine-tuning", two_papers, lambda *a: None
            )
            return rows, judged

    rows, judged = asyncio.run(run())

    cells = rows[0]["values"]
    assert cells[two_papers[0]]["value"] == "Low-rank adapters"
    # An unsourced model value falls back to a quoted sentence from the paper.
    assert cells[two_papers[1]]["value"] != "Invented without a source"
    assert cells[two_papers[1]]["chunk_id"]
    assert [e["document_id"] for e in judged["supports"]] == [two_papers[0]]
    assert [e["document_id"] for e in judged["contradicts"]] == [two_papers[1]]
    assert (judged["summary"], judged["summary_highlight"]) == (
        "The evidence is mixed: it holds for math, not for code.",
        "mixed",
    )
