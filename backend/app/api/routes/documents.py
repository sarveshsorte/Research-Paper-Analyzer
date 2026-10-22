import hashlib
from typing import Annotated, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.app.api.deps import Owner, ServicesDep, Store
from backend.app.services.container import Services
from backend.app.services.runtime import run_in_background, title_from_filename
from backend.app.services.search import DownloadError, SearchError

router = APIRouter(prefix="/api/v1", tags=["documents"])
MAX_BYTES = 25 * 1024 * 1024
MAX_FILES = 5


class FetchBody(BaseModel):
    url: str = Field(min_length=4, max_length=2000)


@router.get("/documents")
async def list_documents(
    store: Store,
    owner: Owner,
    status: Literal["processing", "ready", "failed"] | None = None,
) -> list[dict]:
    return store.list_documents(owner, status)


@router.get("/documents/{document_id}")
async def get_document(document_id: str, store: Store, owner: Owner) -> dict:
    document = store.get_document(document_id, owner)
    if not document:
        raise HTTPException(404, "Document not found.")
    return {
        "document_id": document["document_id"],
        "status": document["status"],
        "pages": document["pages"],
        "chunks": document["chunks"] or 0,
        "sections": store.sections(document_id),
        "error": document["error"],
    }


@router.get("/documents/{document_id}/file")
async def get_document_file(document_id: str, store: Store, owner: Owner) -> Response:
    content = store.get_file(document_id, owner)
    if content is None:
        raise HTTPException(404, "Document file not found.")
    # The stored id names the file, never the uploaded file name.
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{document_id}.pdf"'},
    )


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: str, store: Store, owner: Owner, services: ServicesDep
) -> Response:
    if not store.delete_document(document_id, owner):
        raise HTTPException(404, "Document not found.")
    await services.documents.delete_index(document_id)
    return Response(status_code=204)


@router.post("/upload", status_code=202)
async def upload(
    store: Store,
    owner: Owner,
    services: ServicesDep,
    files: Annotated[list[UploadFile], File()],
) -> list[dict[str, str]]:
    if not files or len(files) > MAX_FILES:
        raise HTTPException(400, f"Upload between 1 and {MAX_FILES} PDFs.")
    received = []
    for upload_file in files:
        name = upload_file.filename or "File"
        content = await upload_file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(413, f"{name} is over 25 MB.")
        if not name.lower().endswith(".pdf") or not content.startswith(b"%PDF-"):
            raise HTTPException(415, f"{name} is not a PDF.")
        received.append((name, content))

    accepted = []
    for name, content in received:
        sha256 = hashlib.sha256(content).hexdigest()
        document = store.find_document(owner, sha256=sha256)
        if document is None:
            document = store.create_document(name, content, owner, sha256=sha256)
            run_in_background(services.documents.process(document["document_id"]))
        elif document["status"] == "failed":
            # The same file failed before: try it again.
            store.update_document(
                document["document_id"], status="processing", error=None
            )
            run_in_background(services.documents.process(document["document_id"]))
            document["status"] = "processing"
        accepted.append(
            {
                "document_id": document["document_id"],
                "filename": name,
                "status": document["status"],
            }
        )
    return accepted


async def _download_and_process(
    services: Services, document_id: str, pdf_url: str
) -> None:
    try:
        content, sha256 = await services.downloader.download(pdf_url)
    except DownloadError as exc:
        services.store.mark_failed(document_id, str(exc))
        return
    services.store.set_file(document_id, content, sha256)
    await services.documents.process(document_id)


@router.post("/documents/fetch", status_code=202)
async def fetch_document(
    body: FetchBody, store: Store, owner: Owner, services: ServicesDep
) -> dict:
    """Adds a paper from an arXiv URL, DOI, Semantic Scholar link or PDF link."""
    try:
        hit = await services.search.resolve_link(body.url)
    except SearchError as exc:
        raise HTTPException(400, str(exc)) from exc
    pdf_url = services.downloader.normalize(hit.pdf_url or "")
    if pdf_url is None:
        raise HTTPException(400, "No open-access PDF is available for that link.")
    existing = store.find_document(owner, url=pdf_url)
    if existing and existing["status"] != "failed":
        return existing
    title = (
        hit.title
        if hit.source != "link" or hit.arxiv_id
        else title_from_filename(hit.title)
    )
    document = store.create_document(
        f"{hit.arxiv_id or 'paper'}.pdf",
        None,
        owner,
        "link",
        title=title,
        url=pdf_url,
        authors=hit.authors_text(),
        year=hit.year,
    )
    run_in_background(_download_and_process(services, document["document_id"], pdf_url))
    return document


@router.post("/documents/{document_id}/retry", status_code=202)
async def retry_document(
    document_id: str, store: Store, owner: Owner, services: ServicesDep
) -> dict:
    document = store.get_document(document_id, owner)
    if not document:
        raise HTTPException(404, "Document not found.")
    if document["status"] == "processing":
        return document
    store.update_document(document_id, status="processing", progress=0, error=None)
    if store.get_file(document_id, owner) is not None:
        run_in_background(services.documents.process(document_id))
    elif document.get("url"):
        run_in_background(_download_and_process(services, document_id, document["url"]))
    else:
        store.mark_failed(document_id, "The PDF file is missing. Upload it again.")
    return store.get_document(document_id, owner) or document


@router.get("/chunks/{chunk_id}")
async def get_chunk(chunk_id: str, store: Store, owner: Owner) -> dict:
    chunk = store.chunk(chunk_id, owner)
    if not chunk:
        raise HTTPException(404, "Chunk not found.")
    return chunk
