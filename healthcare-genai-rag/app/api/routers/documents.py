from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import Document
from app.schemas.documents import DocumentCreateResponse, DocumentReadResponse

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentCreateResponse)
def create_document(file: UploadFile = File(...), db: Session = Depends(get_db)) -> DocumentCreateResponse:
    original_filename = file.filename or "unknown.pdf"
    content_type = file.content_type or "application/octet-stream"

    doc = Document(
        filename=original_filename,
        content_type=content_type,
        status="created",
        storage_path="",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    uploads_dir = Path("data") / "uploads" / doc.id
    uploads_dir.mkdir(parents=True, exist_ok=True)

    storage_path = uploads_dir / "original.pdf"
    with storage_path.open("wb") as f:
        f.write(file.file.read())

    doc.storage_path = str(storage_path)
    doc.status = "uploaded"
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return DocumentCreateResponse(
        document_id=doc.id,
        filename=doc.filename,
        status=doc.status,
        content_type=doc.content_type,
    )


@router.get("/{document_id}", response_model=DocumentReadResponse)
def get_document(document_id: str, db: Session = Depends(get_db)) -> DocumentReadResponse:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentReadResponse(
        document_id=doc.id,
        filename=doc.filename,
        status=doc.status,
        content_type=doc.content_type,
        created_at=doc.created_at,
    )


@router.get("/{document_id}/file")
def get_document_file_inline(document_id: str, db: Session = Depends(get_db)) -> FileResponse:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if not doc.storage_path:
        raise HTTPException(status_code=409, detail="Document has no stored file yet")

    path = Path(doc.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored file not found on disk")

    return FileResponse(
        path=path,
        media_type=doc.content_type or "application/octet-stream",
        filename=doc.filename,
        content_disposition_type="inline",
    )


@router.get("/{document_id}/file/download")
def download_document_file(document_id: str, db: Session = Depends(get_db)) -> FileResponse:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if not doc.storage_path:
        raise HTTPException(status_code=409, detail="Document has no stored file yet")

    path = Path(doc.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored file not found on disk")

    return FileResponse(
        path=path,
        media_type=doc.content_type or "application/octet-stream",
        filename=doc.filename,
        content_disposition_type="attachment",
    )