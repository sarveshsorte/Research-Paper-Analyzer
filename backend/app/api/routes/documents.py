from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from backend.app.api.deps import Owner, Store
from backend.app.services.runtime import run_in_background

router = APIRouter(prefix="/api/v1", tags=["documents"])
MAX_BYTES = 25 * 1024 * 1024


@router.get("/documents")
async def list_documents(store: Store, owner: Owner) -> list[dict]:
    return store.list_documents(owner)


@router.get("/documents/{document_id}")
async def get_document(document_id: str, store: Store, owner: Owner) -> dict:
    document = store.get_document(document_id, owner)
    if not document:
        raise HTTPException(404, "Document not found.")
    document["sections"] = store.sections(document_id)
    return {
        "document_id": document["document_id"],
        "status": document["status"],
        "pages": document["pages"],
        "chunks": document["chunks"] or 0,
        "sections": document["sections"],
        "error": document["error"],
    }


@router.get("/documents/{document_id}/file")
async def get_document_file(document_id: str, store: Store, owner: Owner) -> Response:
    content = store.get_file(document_id, owner)
    if content is None:
        raise HTTPException(404, "Document file not found.")
    return Response(content, media_type="application/pdf")


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str, store: Store, owner: Owner) -> Response:
    if not store.delete_document(document_id, owner):
        raise HTTPException(404, "Document not found.")
    return Response(status_code=204)


@router.post("/upload", status_code=202)
async def upload(
    store: Store, owner: Owner, files: list[UploadFile] = File(...)
) -> list[dict[str, str]]:
    if not files or len(files) > 5:
        raise HTTPException(400, "Upload between 1 and 5 PDFs.")
    accepted = []
    for upload_file in files:
        if not upload_file.filename or not upload_file.filename.lower().endswith(".pdf"):
            raise HTTPException(415, f"{upload_file.filename or 'File'} is not a PDF.")
        content = await upload_file.read()
        if len(content) > MAX_BYTES:
            raise HTTPException(413, f"{upload_file.filename} is over 25 MB.")
        document = store.create_document(upload_file.filename, content, owner)
        accepted.append({
            "document_id": document["document_id"],
            "filename": document["filename"],
            "status": "processing",
        })
        run_in_background(store.process(document["document_id"]))
    return accepted


@router.get("/chunks/{chunk_id}")
async def get_chunk(chunk_id: str, store: Store, owner: Owner) -> dict:
    chunk = store.chunk(chunk_id, owner)
    if not chunk:
        raise HTTPException(404, "Chunk not found.")
    return chunk
