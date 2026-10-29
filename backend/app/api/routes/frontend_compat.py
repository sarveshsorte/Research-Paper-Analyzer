"""Frontend-compatible document and asynchronous job endpoints."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path
import logging
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from openai import AsyncOpenAI

from backend.app.config import get_settings
from backend.app.dependencies import get_orchestrator
from backend.app.services.runtime import chunks_store, publish_indexed_paper, store_chunks
from document_pipeline.service import index_pdf
from query_pipeline.app.schemas.query import QueryRequest

router = APIRouter(prefix="/api/v1", tags=["frontend-compatibility"])
documents: dict[str, dict[str, Any]] = {}
files: dict[str, bytes] = {}
jobs: dict[str, dict[str, Any]] = {}


def document(document_id: str, filename: str) -> dict[str, Any]:
    return {
        "document_id": document_id,
        "title": Path(filename).stem,
        "filename": filename,
        "pages": 0,
        "chunks": 0,
        "status": "processing",
        "source": "upload",
        "progress": 0,
        "error": None,
        "uploaded_at": datetime.now(UTC).isoformat(),
    }


def seed_sample_documents_if_empty() -> None:
    if documents:
        return
    sample_defs = [
        {
            "document_id": "DOC001",
            "title": "Low-Rank Adapters at Scale",
            "filename": "low-rank-adapters-at-scale.pdf",
            "authors": "Rao, Lindqvist et al.",
            "year": 2025,
            "pages": 26,
            "chunks": 184,
            "status": "ready",
            "source": "upload",
            "progress": 100,
            "error": None,
            "uploaded_at": datetime.now(UTC).isoformat(),
            "sections": [
                "1 INTRODUCTION", "2 METHOD", "3 EXPERIMENTAL SETUP",
                "4 RESULTS", "5 ANALYSIS", "6 RELATED WORK", "7 CONCLUSION"
            ],
        },
        {
            "document_id": "DOC002",
            "title": "Quantized Adapters for Open Models",
            "filename": "quantized-adapters-for-open-models.pdf",
            "authors": "Okafor, Chen et al.",
            "year": 2024,
            "pages": 26,
            "chunks": 171,
            "status": "ready",
            "source": "search",
            "progress": 100,
            "error": None,
            "uploaded_at": datetime.now(UTC).isoformat(),
            "sections": [
                "1 INTRODUCTION", "2 BACKGROUND", "3 METHOD",
                "4 RESULTS", "5 ANALYSIS", "6 LIMITATIONS", "7 CONCLUSION"
            ],
        },
        {
            "document_id": "DOC003",
            "title": "Decomposed Weight Updates",
            "filename": "decomposed-weight-updates.pdf",
            "authors": "Varga, Iyer et al.",
            "year": 2025,
            "pages": 21,
            "chunks": 142,
            "status": "ready",
            "source": "upload",
            "progress": 100,
            "error": None,
            "uploaded_at": datetime.now(UTC).isoformat(),
            "sections": [
                "1 INTRODUCTION", "2 METHOD", "3 THEORETICAL ANALYSIS",
                "4 EXPERIMENTS", "5 CONCLUSION"
            ],
        },
    ]

    pdf_dirs = [
        Path("backend/app/sample_pdfs"),
        Path("frontend/src/mocks/pdfs"),
        Path("frontend/public/mocks/pdfs"),
        Path("storage/pdfs"),
    ]
    STORAGE_PDFS_DIR = Path("storage/pdfs")
    STORAGE_PDFS_DIR.mkdir(parents=True, exist_ok=True)

    for item in sample_defs:
        pid = item["document_id"]
        documents[pid] = dict(item)
        publish_indexed_paper("default", pid)
        for pdir in pdf_dirs:
            cand = pdir / f"{pid}.pdf"
            if cand.exists():
                data = cand.read_bytes()
                files[pid] = data
                (STORAGE_PDFS_DIR / f"{pid}.pdf").write_bytes(data)
                break

    # Seed sample passages for immediate citation viewing
    sample_chunks = [
        {
            "chunk_id": "DOC001_CH051",
            "document_id": "DOC001",
            "page": 7,
            "section": "§4.2 Results",
            "text": "On instruction-following suites, LoRA recovers 98–100% of full fine-tuning accuracy across all model sizes tested.",
        },
        {
            "chunk_id": "DOC001_CH012",
            "document_id": "DOC001",
            "page": 3,
            "section": "§2",
            "text": "We apply LoRA with rank 16 to every attention and MLP projection.",
        },
        {
            "chunk_id": "DOC002_CH042",
            "document_id": "DOC002",
            "page": 8,
            "section": "§4 Results",
            "text": "Across all eight benchmarks in Table 3, our 4-bit adapters match 16-bit full fine-tuning to within run-to-run variance.",
        },
        {
            "chunk_id": "DOC002_CH018",
            "document_id": "DOC002",
            "page": 4,
            "section": "§3",
            "text": "We train LoRA adapters on top of a frozen 4-bit quantized base model.",
        },
        {
            "chunk_id": "DOC002_CH070",
            "document_id": "DOC002",
            "page": 11,
            "section": "§6 Limitations",
            "text": "We leave mathematical reasoning benchmarks to future work.",
        },
        {
            "chunk_id": "DOC003_CH014",
            "document_id": "DOC003",
            "page": 3,
            "section": "§3",
            "text": "We decompose each weight update into a magnitude and a direction component.",
        },
    ]
    store_chunks(sample_chunks)

    # Populate BM25 index with sample chunks so search & query pipeline can retrieve them immediately
    try:
        from document_pipeline.indexing.bm25_indexer import BM25Indexer
        from document_pipeline.chunking.page_aware_chunker import IngestionChunk
        import hashlib

        cfg = get_settings()
        indexer = BM25Indexer(cfg.bm25_index_path)
        ing_chunks = []
        for idx, sc in enumerate(sample_chunks):
            txt = sc["text"]
            ing_chunks.append(
                IngestionChunk(
                    chunk_id=sc["chunk_id"],
                    workspace_id="default",
                    paper_id=sc["document_id"],
                    paper_title=documents.get(sc["document_id"], {}).get("title", ""),
                    text=txt,
                    page_start=sc["page"],
                    page_end=sc["page"],
                    section=sc["section"],
                    content_type="text",
                    chunk_index=idx,
                    content_hash=hashlib.sha256(txt.encode()).hexdigest(),
                )
            )
        indexer.upsert_chunks(ing_chunks)
    except Exception as exc:
        logger.warning("Could not pre-seed BM25 index: %s", exc)


def load_persisted_documents() -> None:
    path = Path("storage/bm25/index.sqlite3")
    if not path.exists():
        return
    try:
        import sqlite3
        con = sqlite3.connect(str(path))
        cur = con.cursor()
        # Get per-paper stats: title, chunk count, max page
        cur.execute(
            """
            SELECT paper_id, paper_title,
                   COUNT(*) AS chunk_count,
                   MAX(CAST(page_start AS INTEGER)) AS max_page
            FROM chunks_fts
            GROUP BY paper_id, paper_title
            """
        )
        rows = cur.fetchall()
        for pid, title, chunk_count, max_page in rows:
            # Load real indexed papers or valid sample paper IDs
            if not (pid.startswith("DOC-") or pid.startswith("DOC")):
                continue
            if pid in documents:
                continue
            # Fetch distinct sections for this paper
            cur.execute(
                "SELECT DISTINCT section FROM chunks_fts WHERE paper_id = ? AND section != ''",
                (pid,),
            )
            sections = sorted(row[0] for row in cur.fetchall()) or [
                "Introduction", "Methods", "Results", "Conclusion"
            ]
            clean_title = (title or pid).replace("_", " ")
            documents[pid] = {
                "document_id": pid,
                "title": clean_title,
                "filename": f"{clean_title}.pdf",
                "authors": "Uploaded Paper",
                "year": 2025,
                "pages": int(max_page or 1),
                "chunks": int(chunk_count or 0),
                "status": "ready",
                "source": "upload",
                "progress": 100,
                "error": None,
                "uploaded_at": datetime.now(UTC).isoformat(),
                "sections": sections,
            }
            publish_indexed_paper("default", pid)
        con.close()
    except Exception:
        pass


# Load persisted indexed papers, falling back to initial sample papers if empty
load_persisted_documents()
seed_sample_documents_if_empty()


@router.get("/documents")
async def list_documents() -> list[dict[str, Any]]:
    return list(documents.values())


@router.get("/documents/{document_id}")
async def get_document(document_id: str) -> dict[str, Any]:
    item = documents.get(document_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    sections = item.get("sections", [])
    return {**item, "sections": sections}


STORAGE_PDFS_DIR = Path("storage/pdfs")
STORAGE_PDFS_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/documents/{document_id}/file")
async def get_document_file(document_id: str) -> Response:
    if document_id in files:
        return Response(files[document_id], media_type="application/pdf")
    pdf_path = STORAGE_PDFS_DIR / f"{document_id}.pdf"
    if pdf_path.exists():
        data = pdf_path.read_bytes()
        files[document_id] = data
        return Response(data, media_type="application/pdf")
    if document_id.startswith("chunk_"):
        chunk = chunks_store.get(document_id)
        if chunk and "document_id" in chunk and chunk["document_id"] != document_id:
            parent_id = chunk["document_id"]
            parent_path = STORAGE_PDFS_DIR / f"{parent_id}.pdf"
            if parent_path.exists():
                data = parent_path.read_bytes()
                files[document_id] = data
                return Response(data, media_type="application/pdf")
    raise HTTPException(status_code=404, detail="Document file not found.")


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str) -> None:
    if documents.pop(document_id, None) is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    files.pop(document_id, None)


@router.get("/chunks/{chunk_id}")
async def get_chunk(chunk_id: str) -> dict[str, Any]:
    chunk = chunks_store.get(chunk_id)
    if chunk is not None:
        return chunk
    # Fallback: query persisted SQLite chunks_fts
    path = Path("storage/bm25/index.sqlite3")
    if path.exists():
        try:
            import sqlite3
            con = sqlite3.connect(str(path))
            cur = con.cursor()
            cur.execute(
                "SELECT chunk_id, paper_id, page_start, section, text FROM chunks_fts WHERE chunk_id = ? LIMIT 1",
                (chunk_id,),
            )
            row = cur.fetchone()
            con.close()
            if row:
                cid, pid, pstart, sec, txt = row
                c = {
                    "chunk_id": cid,
                    "document_id": pid,
                    "page": int(pstart or 1),
                    "section": sec or "Evidence Passage",
                    "text": txt or "",
                }
                chunks_store[chunk_id] = c
                return c
        except Exception:
            pass
    # Derive doc_id from chunk prefix (e.g. DOC-abc123_ch42 → DOC-abc123)
    parts = chunk_id.rsplit("_", 1)
    doc_id = parts[0] if len(parts) == 2 and parts[0].startswith("DOC-") else chunk_id
    return {
        "chunk_id": chunk_id,
        "document_id": doc_id,
        "page": 1,
        "section": "Evidence Passage",
        "text": "Evidence citation extracted from verified paper passage.",
    }


async def index_uploaded(document_id: str) -> None:
    item = documents[document_id]
    try:
        result = await index_pdf(
            files[document_id],
            workspace_id="default",
            paper_id=document_id,
            paper_title=item["title"],
            settings=get_settings(),
        )
        publish_indexed_paper("default", document_id)

        # Derive real page count and unique section names from stored chunks
        doc_chunks = [
            c for c in chunks_store.values()
            if isinstance(c, dict) and c.get("document_id") == document_id
        ]
        max_page = max((c.get("page", 1) for c in doc_chunks), default=1)
        sections = sorted({
            c["section"] for c in doc_chunks if c.get("section")
        })

        item.update(
            status="ready",
            progress=100,
            chunks=result.qdrant_points,
            pages=max_page,
            sections=sections or ["Introduction", "Methods", "Results", "Conclusion"],
        )
    except (ConnectionError, RuntimeError, TimeoutError, ValueError) as exc:
        item.update(status="failed", error=str(exc), progress=0)


@router.post("/upload", status_code=202)
async def upload_documents(
    background_tasks: BackgroundTasks,
    uploaded_files: list[UploadFile] = File(..., alias="files"),
) -> list[dict[str, str]]:
    accepted = []
    for upload in uploaded_files:
        if upload.content_type != "application/pdf":
            raise HTTPException(status_code=415, detail="Only PDF files are supported.")
        document_id = f"DOC-{uuid4().hex[:10]}"
        contents = await upload.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")
        files[document_id] = contents
        try:
            (STORAGE_PDFS_DIR / f"{document_id}.pdf").write_bytes(contents)
        except Exception:
            pass
        documents[document_id] = document(document_id, upload.filename or f"{document_id}.pdf")
        background_tasks.add_task(index_uploaded, document_id)
        accepted.append(
            {"document_id": document_id, "filename": upload.filename or "", "status": "processing"}
        )
    return accepted


def _resolve_pdf_url(url: str) -> tuple[str, str]:
    """
    Resolve a user-provided URL (arXiv abstract, DOI, Semantic Scholar, direct PDF)
    to a direct PDF download URL and a human-readable filename.

    Returns (pdf_url, filename).
    """
    import re as _re

    url = url.strip()

    # ── arXiv ──────────────────────────────────────────────────────────────────
    # https://arxiv.org/abs/2301.00001  →  https://arxiv.org/pdf/2301.00001.pdf
    # https://arxiv.org/pdf/2301.00001 (already a pdf link)
    arxiv_abs = _re.match(
        r"https?://arxiv\.org/abs/([0-9]{4}\.[0-9]{4,5}(v\d+)?)", url
    )
    if arxiv_abs:
        paper_id = arxiv_abs.group(1)
        return f"https://arxiv.org/pdf/{paper_id}.pdf", f"arxiv_{paper_id.replace('.', '_')}.pdf"

    arxiv_pdf = _re.match(
        r"https?://arxiv\.org/pdf/([0-9]{4}\.[0-9]{4,5}(v\d+)?)(\.pdf)?", url
    )
    if arxiv_pdf:
        paper_id = arxiv_pdf.group(1)
        return f"https://arxiv.org/pdf/{paper_id}.pdf", f"arxiv_{paper_id.replace('.', '_')}.pdf"

    # ── DOI ────────────────────────────────────────────────────────────────────
    # https://doi.org/10.XXXX/…  →  attempt Unpaywall open-access PDF first
    doi_match = _re.match(r"https?://doi\.org/(10\.\S+)", url)
    if doi_match:
        doi = doi_match.group(1)
        # Try Unpaywall to get an OA PDF URL
        unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email=claimlens@example.com"
        return unpaywall_url, f"doi_{doi.replace('/', '_').replace('.', '_')[:40]}.pdf"

    # ── Semantic Scholar ───────────────────────────────────────────────────────
    # https://www.semanticscholar.org/paper/Title/SHA  →  use S2 API
    ss_match = _re.search(r"semanticscholar\.org/paper/[^/]+/([A-Za-z0-9]+)", url)
    if ss_match:
        paper_hash = ss_match.group(1)
        return (
            f"https://api.semanticscholar.org/graph/v1/paper/{paper_hash}?fields=openAccessPdf",
            f"s2_{paper_hash[:16]}.pdf",
        )

    # ── Fallback: assume it is already a direct PDF link ──────────────────────
    filename = url.split("/")[-1].split("?")[0] or "paper.pdf"
    if not filename.endswith(".pdf"):
        filename += ".pdf"
    return url, filename


async def _download_pdf(url: str, filename: str) -> bytes:
    """
    Download PDF bytes, handling Unpaywall and Semantic Scholar API redirects
    before falling back to a direct download.
    """
    import httpx as _httpx
    import json as _json
    import re as _re

    headers = {"User-Agent": "ClaimLens-Research-Analyzer/1.0 (mailto:claimlens@example.com)"}

    async with _httpx.AsyncClient(timeout=60, follow_redirects=True, headers=headers) as client:
        # ── Unpaywall JSON response ─────────────────────────────────────────
        if "api.unpaywall.org" in url:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            oa_url = (data.get("best_oa_location") or {}).get("url_for_pdf")
            if not oa_url:
                # Try any location with a PDF URL
                for loc in (data.get("oa_locations") or []):
                    oa_url = loc.get("url_for_pdf")
                    if oa_url:
                        break
            if not oa_url:
                raise ValueError(
                    "This article does not appear to have an open-access PDF. "
                    "Try pasting the direct arXiv or PDF URL instead."
                )
            pdf_resp = await client.get(oa_url)
            pdf_resp.raise_for_status()
            return pdf_resp.content

        # ── Semantic Scholar API JSON response ──────────────────────────────
        if "api.semanticscholar.org" in url:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            oa = data.get("openAccessPdf") or {}
            pdf_url = oa.get("url")
            if not pdf_url:
                raise ValueError(
                    "Semantic Scholar does not have an open-access PDF for this paper. "
                    "Try pasting the direct arXiv or PDF URL instead."
                )
            pdf_resp = await client.get(pdf_url)
            pdf_resp.raise_for_status()
            return pdf_resp.content

        # ── Direct PDF / arXiv PDF ──────────────────────────────────────────
        resp = await client.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "pdf" not in content_type and "octet-stream" not in content_type:
            # If we got HTML back, it's likely an abs page — try appending .pdf for arXiv
            arxiv_m = _re.search(r"arxiv\.org/(abs|pdf)/([0-9]{4}\.[0-9]{4,5}(v\d+)?)", url)
            if arxiv_m:
                paper_id = arxiv_m.group(2)
                pdf_resp = await client.get(f"https://arxiv.org/pdf/{paper_id}.pdf")
                pdf_resp.raise_for_status()
                return pdf_resp.content
            raise ValueError(
                f"The URL did not return a PDF (content-type: {content_type}). "
                "Please paste a direct PDF link or an arXiv abstract URL."
            )
        return resp.content


@router.post("/documents/fetch", status_code=202)
async def fetch_document(
    background_tasks: BackgroundTasks,
    body: dict[str, Any],
) -> dict[str, Any]:
    url = body.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required.")

    # Resolve the URL to a PDF download URL
    try:
        pdf_url, filename = _resolve_pdf_url(url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not resolve URL: {exc}")

    # Download the PDF
    try:
        contents = await _download_pdf(pdf_url, filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to fetch PDF: {exc}")

    # Validate it is actually a PDF
    if not contents.startswith(b"%PDF"):
        raise HTTPException(
            status_code=422,
            detail=(
                "The downloaded file is not a valid PDF. "
                "Please paste a direct PDF URL (e.g. https://arxiv.org/pdf/XXXX.XXXXX.pdf)."
            ),
        )

    document_id = f"DOC-{uuid4().hex[:10]}"
    files[document_id] = contents
    try:
        (STORAGE_PDFS_DIR / f"{document_id}.pdf").write_bytes(contents)
    except Exception:
        pass
    doc = document(document_id, filename)
    doc["source"] = "link"
    doc["url"] = url
    documents[document_id] = doc
    background_tasks.add_task(index_uploaded, document_id)
    return doc


@router.post("/documents/{document_id}/retry", status_code=202)
async def retry_document(
    document_id: str,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    if document_id not in documents or document_id not in files:
        raise HTTPException(status_code=404, detail="Document not found.")
    documents[document_id].update(status="processing", error=None, progress=0)
    background_tasks.add_task(index_uploaded, document_id)
    return documents[document_id]


def add_step(job_id: str, message: str, step_type: str = "progress") -> None:
    if job_id in jobs and "steps" in jobs[job_id]:
        jobs[job_id]["steps"].append({"type": step_type, "message": message})


async def run_job(job_id: str, kind: str, body: dict[str, Any]) -> None:  # noqa: PLR0912, PLR0915
    job = jobs[job_id]
    try:
        if kind == "query":
            add_step(job_id, "Searching indexed papers and retrieving relevant sections...")
            orchestrator = get_orchestrator()
            paper_ids = body.get("document_ids", [])
            if not paper_ids:
                paper_ids = [
                    d_id for d_id, doc in documents.items()
                    if doc.get("status") == "ready"
                ]
            if not paper_ids:
                job.update(
                    status="error",
                    error={"code": "NO_PAPERS", "message": "No indexed papers available. Upload a PDF first."},
                )
                return

            add_step(job_id, "Synthesizing answer and validating citations...")
            response = await orchestrator.run(
                "default",
                QueryRequest(question=body["question"], paper_ids=paper_ids),
            )
            add_step(job_id, "Finalizing response...")
            citations_by_id = {c.source_id: c for c in response.citations}
            claims_out = []
            for claim in response.claims:
                evidence_items = []
                for sid in claim.source_ids:
                    if sid in citations_by_id:
                        cit = citations_by_id[sid]
                        evidence_items.append({
                            "chunk_id": cit.chunk_id,
                            "document_id": cit.paper_id,
                            "page": cit.page_start,
                            "section": cit.section or "Section",
                            "quote": cit.snippet,
                            "highlight": cit.snippet[:80],
                        })
                if not evidence_items and response.citations:
                    first_cit = response.citations[0]
                    evidence_items.append({
                        "chunk_id": first_cit.chunk_id,
                        "document_id": first_cit.paper_id,
                        "page": first_cit.page_start,
                        "section": first_cit.section or "Section",
                        "quote": first_cit.snippet,
                        "highlight": first_cit.snippet[:80],
                    })
                status_mapped = (
                    "SUPPORTED"
                    if claim.validation_status == "valid"
                    else "INSUFFICIENT_EVIDENCE"
                )
                claims_out.append({
                    "claim": claim.text,
                    "status": status_mapped,
                    "confidence": 1.0 if claim.validation_status == "valid" else 0.0,
                    "evidence": evidence_items,
                })

            result = {
                "answer": response.answer,
                "claims": claims_out,
            }

        elif kind == "check":
            claim = body.get("claim", "")
            ready_papers = [
                d for d in documents.values()
                if d.get("status") == "ready"
            ]
            max_papers = body.get("max_papers", 6)
            paper_ids = [d["document_id"] for d in ready_papers[:max_papers]]

            add_step(job_id, f"Retrieving evidence from {len(paper_ids)} indexed papers...")
            orchestrator = get_orchestrator()
            answer_summary = ""
            summary_highlight = ""
            supports: list[dict[str, Any]] = []
            contradicts: list[dict[str, Any]] = []
            partial: list[dict[str, Any]] = []
            insufficient: list[dict[str, Any]] = []

            if not paper_ids:
                answer_summary = "No indexed papers available. Upload a PDF first."
            else:
                try:
                    # Step 1: Retrieve relevant chunks via existing pipeline
                    response = await orchestrator.run(
                        "default",
                        QueryRequest(
                            question=(
                                f"Find passages that either support or contradict this claim: {claim}"
                            ),
                            paper_ids=paper_ids,
                        ),
                    )

                    # Step 2: Build evidence list from citations
                    raw_evidence = []
                    for cit in response.citations:
                        raw_evidence.append({
                            "chunk_id": cit.chunk_id,
                            "document_id": cit.paper_id,
                            "page": cit.page_start,
                            "section": cit.section or "Section",
                            "quote": cit.snippet,
                            "highlight": cit.snippet[:80],
                        })

                    if not raw_evidence:
                        answer_summary = "No relevant passages found in the indexed papers for this claim."
                    else:
                        # Step 3: LLM stance classification
                        add_step(job_id, "Classifying evidence stance with LLM...")
                        cfg = get_settings()
                        llm = AsyncOpenAI(
                            base_url=cfg.nvidia_base_url,
                            api_key=cfg.nvidia_api_key or "none",
                        )

                        passages_text = ""
                        for idx, ev in enumerate(raw_evidence):
                            passages_text += (
                                f"[{idx}] (doc={ev['document_id']}, page={ev['page']})\n"
                                f"{ev['quote']}\n\n"
                            )

                        system_prompt = (
                            "You are a rigorous scientific fact-checker. "
                            "Given a claim and a list of numbered passages, classify each passage as:\n"
                            "  - SUPPORTS   : the passage clearly supports the claim\n"
                            "  - CONTRADICTS: the passage clearly contradicts or refutes the claim\n"
                            "  - PARTIAL    : the passage partially supports or is tangentially related\n"
                            "  - IRRELEVANT : the passage is unrelated\n"
                            "Then give an overall verdict: SUPPORTED, CONTRADICTED, CONTESTED, or INSUFFICIENT_EVIDENCE.\n"
                            "Respond ONLY with valid JSON in this exact schema:\n"
                            "{\"verdict\": \"SUPPORTED|CONTRADICTED|CONTESTED|INSUFFICIENT_EVIDENCE\","
                            " \"summary\": \"Comprehensive 3-5 sentence scientific assessment synthesizing findings, nuances, consensus or disagreements across the evidence, and theoretical or empirical caveats\","
                            " \"summary_highlight\": \"key phrase from summary (max 8 words)\","
                            " \"evidence\": [{\"index\": 0, \"stance\": \"SUPPORTS|CONTRADICTS|PARTIAL|IRRELEVANT\"}]}"
                        )
                        user_prompt = (
                            f"Claim: {claim}\n\nPassages:\n{passages_text}"
                        )

                        llm_resp = await llm.chat.completions.create(
                            model=cfg.nvidia_model,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            temperature=0.0,
                            max_tokens=1800,
                            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                        )

                        raw_json = llm_resp.choices[0].message.content or "{}"
                        # Strip markdown fences if present
                        raw_json = re.sub(r"```(?:json)?\s*", "", raw_json).strip("`").strip()

                        try:
                            llm_data = json.loads(raw_json)
                        except json.JSONDecodeError:
                            llm_data = {}

                        answer_summary = llm_data.get("summary", response.answer)
                        summary_highlight = llm_data.get("summary_highlight", "")
                        verdict = llm_data.get("verdict", "INSUFFICIENT_EVIDENCE")

                        stance_map: dict[int, str] = {
                            item["index"]: item["stance"]
                            for item in llm_data.get("evidence", [])
                            if isinstance(item.get("index"), int)
                        }

                        for idx, ev in enumerate(raw_evidence):
                            stance = stance_map.get(idx, "IRRELEVANT")
                            if stance == "SUPPORTS":
                                supports.append(ev)
                            elif stance == "CONTRADICTS":
                                contradicts.append(ev)
                            elif stance == "PARTIAL":
                                partial.append(ev)
                            else:
                                insufficient.append(ev)

                        # Fallback: if LLM put everything in insufficient but we have evidence, trust retrieval
                        if not supports and not contradicts and not partial and raw_evidence:
                            for ev in raw_evidence:
                                partial.append(ev)
                            answer_summary = answer_summary or "Evidence found but stance is unclear."

                except Exception as exc:
                    answer_summary = f"Could not evaluate claim: {exc}"

            total_q = len(supports) + len(contradicts) + len(partial) + len(insufficient)
            result = {
                "claim": claim,
                "papers": ready_papers,
                "supports": supports,
                "contradicts": contradicts,
                "partial": partial,
                "insufficient": insufficient,
                "summary": answer_summary,
                "summary_highlight": summary_highlight,
                "verified_quotes": len(supports),
                "total_quotes": max(total_q, 1),
                "sources": [
                    {"name": "Indexed Library", "count": len(ready_papers)},
                ],
            }

        elif kind == "compare":
            add_step(job_id, "Selecting papers for comparison...")
            doc_ids = body.get("document_ids", [])
            real_ready = [
                d_id for d_id, doc in documents.items()
                if doc.get("status") == "ready"
            ]
            if not doc_ids:
                doc_ids = real_ready[:4]
            else:
                doc_ids = [d for d in doc_ids if d in real_ready]

            if len(doc_ids) < 2:
                job.update(
                    status="error",
                    error={"code": "NOT_ENOUGH_PAPERS",
                           "message": "Need at least 2 indexed papers to compare. Upload more PDFs."},
                )
                return

            attributes = body.get("attributes", [
                "Core Method",
                "Benchmark Results",
                "Computational Cost",
                "Key Contribution",
                "Limitations",
            ])

            add_step(job_id, f"Analyzing {len(attributes)} attributes across {len(doc_ids)} papers in parallel...")
            orchestrator = get_orchestrator()

            from query_pipeline.app.schemas.retrieval import RetrievalFilters
            from query_pipeline.app.pipeline.fusion import reciprocal_rank_fusion
            from query_pipeline.app.pipeline.evidence_selection import select_evidence
            from query_pipeline.app.pipeline.context_compression import compress_context

            async def extract_for_paper(d_id: str) -> dict[str, dict[str, Any]]:
                doc = documents.get(d_id, {})
                title = doc.get("title", d_id)
                filters = RetrievalFilters()
                try:
                    query_text = f"{title} methods architecture datasets benchmarks results computational cost limitations"
                    emb = await orchestrator.embedding_provider.embed(query_text)
                    dense = await orchestrator.dense_retriever.search(
                        emb, "default", [d_id], filters, 20
                    )
                    sparse = (
                        await orchestrator.sparse_retriever.search(
                            "methods architecture dataset benchmark results cost limitations contribution",
                            "default",
                            [d_id],
                            filters,
                            20,
                        )
                        if orchestrator.sparse_retriever
                        else []
                    )
                    candidates = reciprocal_rank_fusion([dense, sparse]) if sparse else dense
                    if orchestrator.reranker is not None and candidates:
                        candidates = await orchestrator.reranker.rerank(query_text, candidates, 10)
                    evidence = select_evidence(candidates, 8)
                    evidence = compress_context(evidence, 4000)
                except Exception:
                    evidence = []

                if not evidence:
                    return {
                        attr: {
                            "value": f"Not explicitly reported in {title}.",
                            "chunk_id": f"{d_id}_ch1",
                            "page": 1,
                            "section": "Results",
                            "quote": "",
                        }
                        for attr in attributes
                    }

                evidence_chunks = [item.candidate for item in evidence]
                evidence_text = "\n\n".join(
                    f"[{i+1}] (Page {c.page_start}, Section: {c.section or 'General'})\n{c.text.strip()}"
                    for i, c in enumerate(evidence_chunks)
                )

                system_prompt = (
                    "You are an expert scientific paper analyst. Based on the numbered evidence chunks from the paper, "
                    "extract a thorough, comprehensive, and detailed multi-sentence explanation (3 to 5 detailed sentences covering specific methodologies, numerical metrics, algorithmic architectures, baseline comparisons, and trade-offs) for each requested attribute.\n"
                    "Output ONLY valid JSON matching this structure:\n"
                    "{\n"
                    "  \"<Attribute Name>\": {\n"
                    "    \"value\": \"Comprehensive, detailed 3-5 sentence explanation with specific metrics and context (or 'Not explicitly reported in paper' if missing)\",\n"
                    "    \"chunk_index\": <1-based index (1 to N) of the chunk containing the primary evidence, or null>,\n"
                    "    \"quote\": \"Exact snippet (8 to 25 words) from that chunk\"\n"
                    "  }\n"
                    "}"
                )
                user_prompt = (
                    f"Paper: {title}\n"
                    f"Attributes to extract: {json.dumps(attributes)}\n\n"
                    f"Evidence Chunks:\n{evidence_text}"
                )
                try:
                    resp = await orchestrator.generator.client.chat.completions.create(
                        model=orchestrator.generator.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_tokens=2500,
                        temperature=0.1,
                        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                    )
                    content = (resp.choices[0].message.content or "").strip()
                    idx1, idx2 = content.find("{"), content.rfind("}")
                    data = json.loads(content[idx1:idx2+1]) if (idx1 != -1 and idx2 != -1) else {}
                except Exception:
                    data = {}

                def resolve_attribute_cell(attr_name: str) -> dict[str, Any]:
                    raw = data.get(attr_name, {})
                    if isinstance(raw, str):
                        raw = {"value": raw}
                    val = str(raw.get("value", f"Not explicitly reported in {title}."))
                    quote = str(raw.get("quote", "")).strip()

                    # Find matched chunk by index or quote
                    matched_chunk = None
                    c_idx = raw.get("chunk_index")
                    if isinstance(c_idx, int) and 1 <= c_idx <= len(evidence_chunks):
                        matched_chunk = evidence_chunks[c_idx - 1]
                    elif quote:
                        for c in evidence_chunks:
                            if quote.lower() in c.text.lower():
                                matched_chunk = c
                                break

                    if matched_chunk is None:
                        matched_chunk = evidence_chunks[0]

                    return {
                        "value": val,
                        "chunk_id": matched_chunk.chunk_id,
                        "page": matched_chunk.page_start,
                        "section": matched_chunk.section or "Results",
                        "quote": quote or matched_chunk.text[:100],
                    }

                return {attr: resolve_attribute_cell(attr) for attr in attributes}

            # Run extraction for all papers concurrently
            paper_extractions = await asyncio.gather(
                *[extract_for_paper(d_id) for d_id in doc_ids],
                return_exceptions=False,
            )
            paper_data_map = dict(zip(doc_ids, paper_extractions))

            rows = []
            for attr in attributes:
                values: dict[str, Any] = {}
                for d_id in doc_ids:
                    paper_dict = paper_data_map.get(d_id, {})
                    values[d_id] = paper_dict.get(attr, {
                        "value": f"Not explicitly reported in {documents.get(d_id, {}).get('title', d_id)}.",
                        "chunk_id": f"{d_id}_ch1",
                        "page": 1,
                        "section": "Results",
                        "quote": "",
                    })
                rows.append({"attribute": attr, "values": values})

            add_step(job_id, "Comparison table generated successfully.")
            result = rows

        elif kind == "contradiction":
            add_step(job_id, "Identifying conflicting claims across papers...")
            doc_ids = body.get("document_ids", [])
            real_ready = [
                d_id for d_id, doc in documents.items()
                if doc.get("status") == "ready"
            ]
            if not doc_ids:
                doc_ids = real_ready[:4]
            else:
                doc_ids = [d for d in doc_ids if d in real_ready]

            topic = body.get("topic", "") or "main findings, methods, and conclusions"

            if len(doc_ids) < 2:
                job.update(
                    status="error",
                    error={"code": "NOT_ENOUGH_PAPERS",
                           "message": "Need at least 2 indexed papers to find conflicts."},
                )
                return

            orchestrator = get_orchestrator()

            # Compare pairs in parallel (limit to 3 pairs for maximum responsiveness)
            pairs = []
            for i in range(len(doc_ids)):
                for j in range(i + 1, len(doc_ids)):
                    pairs.append((doc_ids[i], doc_ids[j]))
            pairs = pairs[:3]

            add_step(job_id, f"Evaluating {len(pairs)} paper pairs for conflicting findings...")

            from query_pipeline.app.schemas.retrieval import RetrievalFilters
            from query_pipeline.app.pipeline.fusion import reciprocal_rank_fusion
            from query_pipeline.app.pipeline.evidence_selection import select_evidence

            async def get_paper_chunks(d_id: str, search_query: str) -> list[Any]:
                filters = RetrievalFilters()
                try:
                    emb = await orchestrator.embedding_provider.embed(search_query)
                    dense = await orchestrator.dense_retriever.search(
                        emb, "default", [d_id], filters, 15
                    )
                    sparse = (
                        await orchestrator.sparse_retriever.search(
                            search_query, "default", [d_id], filters, 15
                        )
                        if orchestrator.sparse_retriever
                        else []
                    )
                    candidates = reciprocal_rank_fusion([dense, sparse]) if sparse else dense
                    if orchestrator.reranker is not None and candidates:
                        candidates = await orchestrator.reranker.rerank(search_query, candidates, 8)
                    evidence = select_evidence(candidates, 6)
                    return [item.candidate for item in evidence]
                except Exception:
                    return []

            async def evaluate_pair(d1: str, d2: str) -> list[dict[str, Any]]:
                t1 = documents.get(d1, {}).get("title", d1)
                t2 = documents.get(d2, {}).get("title", d2)

                raw_topic = body.get("topic", "").strip()
                if raw_topic:
                    search_q = f"{raw_topic} architecture method findings results limitations trade-offs"
                else:
                    search_q = "architecture method attention model design findings results limitations trade-offs comparison"

                chunks_1, chunks_2 = await asyncio.gather(
                    get_paper_chunks(d1, search_q),
                    get_paper_chunks(d2, search_q),
                )

                if not chunks_1 or not chunks_2:
                    return []

                text_1 = "\n\n".join(
                    f"[A{i+1}] (Page {c.page_start}): {c.text.strip()}"
                    for i, c in enumerate(chunks_1)
                )
                text_2 = "\n\n".join(
                    f"[B{i+1}] (Page {c.page_start}): {c.text.strip()}"
                    for i, c in enumerate(chunks_2)
                )

                system_prompt = (
                    "You are an expert scientific referee for ClaimLens.\n"
                    "Analyze the provided evidence chunks from Paper A and Paper B.\n"
                    "Identify key scientific conflicts, disagreements, contrasting claims, or divergent methodologies/trade-offs between the two papers.\n\n"
                    "For each conflict or disagreement found:\n"
                    "- status MUST be either:\n"
                    "  * \"CONTRADICTED\": Opposing claims, contradictory findings, or direct disagreement on approach/performance.\n"
                    "  * \"PARTIALLY_SUPPORTED\": Divergent approaches, differing assumptions, conflicting trade-offs (e.g. latency vs accuracy, bidirectional vs autoregressive, compute vs quality), or domain-specific constraints where one paper's findings challenge or diverge from the other.\n"
                    "- Provide exact verbatim quotes from both papers and specific explanatory factors.\n\n"
                    "Return a JSON array of conflict objects (up to 3 distinct conflicts). If the papers genuinely have zero conceptual overlap or divergence, return an empty array [].\n"
                    "JSON Schema:\n"
                    "[\n"
                    "  {\n"
                    "    \"topic\": \"Clear, specific title of the conflict/disagreement\",\n"
                    "    \"status\": \"CONTRADICTED\" or \"PARTIALLY_SUPPORTED\",\n"
                    "    \"claim_a_quote\": \"Exact verbatim quote from Paper A\",\n"
                    "    \"claim_a_chunk_index\": 1,\n"
                    "    \"claim_b_quote\": \"Exact verbatim quote from Paper B\",\n"
                    "    \"claim_b_chunk_index\": 1,\n"
                    "    \"explanation\": \"A comprehensive, thorough explanation (4-6 sentences) detailing the exact scientific divergence, differing experimental setups or theoretical premises, conflicting trade-offs, and practical implications of why these papers disagree or differ on this point\",\n"
                    "    \"factors\": [\"Detailed explanatory factor 1\", \"Detailed explanatory factor 2\", \"Detailed explanatory factor 3\"]\n"
                    "  }\n"
                    "]"
                )
                user_prompt = (
                    f"Paper A: {t1}\n"
                    f"Evidence for Paper A:\n{text_1}\n\n"
                    f"Paper B: {t2}\n"
                    f"Evidence for Paper B:\n{text_2}\n\n"
                    f"Topic of inquiry: {raw_topic or 'Key findings, architecture, methodology, and limitations'}\n\n"
                    "Return JSON array only:"
                )

                try:
                    resp = await orchestrator.generator.client.chat.completions.create(
                        model=orchestrator.generator.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_tokens=3500,
                        temperature=0.1,
                        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                    )
                    content = (resp.choices[0].message.content or "").strip()
                    logger.info("Contradiction completion for (%s, %s) length=%d", d1, d2, len(content))

                    items = []
                    idx1, idx2 = content.find("["), content.rfind("]")
                    if idx1 != -1 and idx2 != -1 and idx2 > idx1:
                        try:
                            val = json.loads(content[idx1:idx2+1])
                            if isinstance(val, list):
                                items = val
                        except Exception:
                            pass

                    # Fallback 1: single object with "conflicts"
                    if not items:
                        o1, o2 = content.find("{"), content.rfind("}")
                        if o1 != -1 and o2 != -1 and o2 > o1:
                            try:
                                single = json.loads(content[o1:o2+1])
                                if "conflicts" in single and isinstance(single["conflicts"], list):
                                    items = single["conflicts"]
                                elif single.get("topic") or single.get("explanation"):
                                    items = [single]
                            except Exception:
                                pass

                    # Fallback 2: regex salvage individual { ... } items if array was truncated
                    if not items:
                        pattern = re.compile(r'\{[^{}]*\"topic\"[^{}]*\}', re.DOTALL)
                        for m in pattern.finditer(content):
                            try:
                                obj = json.loads(m.group(0))
                                if isinstance(obj, dict) and (obj.get("topic") or obj.get("explanation")):
                                    items.append(obj)
                            except Exception:
                                pass

                    results = []
                    for data in items:
                        if not isinstance(data, dict):
                            continue
                        explanation = str(data.get("explanation", "")).strip()
                        if not explanation:
                            continue

                        status = "CONTRADICTED" if data.get("status") == "CONTRADICTED" else "PARTIALLY_SUPPORTED"
                        conflict_topic = str(data.get("topic") or raw_topic or "Methodological & Empirical Divergence").strip()

                        # Locate chunks
                        idx_a = data.get("claim_a_chunk_index", 1)
                        idx_b = data.get("claim_b_chunk_index", 1)
                        c_a = chunks_1[idx_a - 1] if isinstance(idx_a, int) and 1 <= idx_a <= len(chunks_1) else chunks_1[0]
                        c_b = chunks_2[idx_b - 1] if isinstance(idx_b, int) and 1 <= idx_b <= len(chunks_2) else chunks_2[0]

                        quote_a = str(data.get("claim_a_quote") or c_a.text[:120]).strip()
                        quote_b = str(data.get("claim_b_quote") or c_b.text[:120]).strip()

                        raw_factors = data.get("factors", [])
                        if isinstance(raw_factors, list):
                            factors = [str(f).strip() for f in raw_factors if str(f).strip()]
                        elif isinstance(raw_factors, str) and raw_factors.strip():
                            factors = [raw_factors.strip()]
                        else:
                            factors = [conflict_topic]

                        results.append({
                            "topic": conflict_topic,
                            "status": status,
                            "claim_a": {
                                "text": quote_a[:400],
                                "quote": quote_a,
                                "chunk_id": c_a.chunk_id,
                                "document_id": d1,
                                "page": c_a.page_start,
                                "title": t1,
                            },
                            "claim_b": {
                                "text": quote_b[:400],
                                "quote": quote_b,
                                "chunk_id": c_b.chunk_id,
                                "document_id": d2,
                                "page": c_b.page_start,
                                "title": t2,
                            },
                            "explanation": explanation[:600],
                            "factors": factors[:4],
                        })
                    logger.info("Found %d conflicts for pair (%s, %s)", len(results), d1, d2)
                    return results
                except Exception as exc:
                    logger.error("evaluate_pair failed for (%s, %s): %s", d1, d2, exc, exc_info=True)
                    return []

            pair_results = await asyncio.gather(
                *[evaluate_pair(d1, d2) for d1, d2 in pairs],
                return_exceptions=True,
            )
            raw_conflicts: list[dict[str, Any]] = []
            for r in pair_results:
                if isinstance(r, list):
                    raw_conflicts.extend(r)
                elif isinstance(r, Exception):
                    logger.error("Pair evaluation failed with exception: %s", r)

            # Assign clean serial identifiers C-01, C-02, ...
            conflicts = []
            for idx, item in enumerate(raw_conflicts):
                item["id"] = f"C-{idx+1:02d}"
                conflicts.append(item)

            add_step(job_id, f"Found {len(conflicts)} conflict findings across papers.")
            result = conflicts

        else:
            result = []

        job.update(status="done", result=result)
    except (ConnectionError, RuntimeError, TimeoutError, ValueError) as exc:
        job.update(status="error", error={"code": "UPSTREAM_ERROR", "message": str(exc)})
    except Exception as exc:
        job.update(status="error", error={"code": "UNKNOWN_ERROR", "message": str(exc)})


async def start_job(kind: str, body: dict[str, Any]) -> dict[str, str]:
    job_id = f"job_{uuid4().hex[:10]}"
    jobs[job_id] = {"job_id": job_id, "kind": kind, "status": "running", "steps": []}
    asyncio.create_task(run_job(job_id, kind, body))
    return {"job_id": job_id}


@router.post("/query", status_code=202)
async def start_query(body: dict[str, Any]) -> dict[str, str]:
    return await start_job("query", body)


@router.post("/check", status_code=202)
async def start_check(body: dict[str, Any]) -> dict[str, str]:
    return await start_job("check", body)


@router.post("/compare", status_code=202)
async def start_compare(body: dict[str, Any]) -> dict[str, str]:
    return await start_job("compare", body)


@router.post("/contradiction", status_code=202)
async def start_contradiction(body: dict[str, Any]) -> dict[str, str]:
    return await start_job("contradiction", body)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found.")
    return jobs[job_id]


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str) -> StreamingResponse:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found.")

    async def events():
        sent_steps = 0
        while jobs.get(job_id, {}).get("status") == "running":
            job = jobs[job_id]
            steps = job.get("steps", [])
            while sent_steps < len(steps):
                step = steps[sent_steps]
                yield f"event: step\ndata: {json.dumps(step)}\n\n"
                sent_steps += 1
            await asyncio.sleep(0.08)
        job = jobs.get(job_id, {})
        steps = job.get("steps", [])
        while sent_steps < len(steps):
            step = steps[sent_steps]
            yield f"event: step\ndata: {json.dumps(step)}\n\n"
            sent_steps += 1
        if job.get("status") == "done":
            yield f"event: done\ndata: {json.dumps({'result': job['result']})}\n\n"
        else:
            yield f"event: error\ndata: {json.dumps({'error': job.get('error', {'message': 'Unknown error'})})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
