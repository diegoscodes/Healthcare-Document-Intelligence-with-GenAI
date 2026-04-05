from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import Document, DocumentPage
from app.schemas.documents import (
    DocumentCreateResponse,
    DocumentPagesReadResponse,
    DocumentPageReadResponse,
    DocumentProcessResponse,
    DocumentReadResponse,
    DocumentIndexResponse,
)
from app.services.document_loader import extract_pdf_pages_text
from app.services.vector_store import index_document_pages_to_weaviate

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


@router.post("/{document_id}/process", response_model=DocumentProcessResponse)
def process_document(document_id: str, db: Session = Depends(get_db)) -> DocumentProcessResponse:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if not doc.storage_path:
        raise HTTPException(status_code=409, detail="Document has no stored file yet")

    pdf_path = Path(doc.storage_path)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Stored file not found on disk")

    try:
        pages_text = extract_pdf_pages_text(pdf_path)
    except Exception as e:
        doc.status = "error"
        db.add(doc)
        db.commit()
        raise HTTPException(status_code=422, detail=f"Failed to parse PDF: {e!s}") from e

    # MVP: delete existing pages then insert fresh ones
    db.query(DocumentPage).filter(DocumentPage.document_id == doc.id).delete(synchronize_session=False)

    total_chars = 0
    for i, text in enumerate(pages_text, start=1):
        total_chars += len(text)
        db.add(
            DocumentPage(
                document_id=doc.id,
                page_number=i,
                text=text,
            )
        )

    doc.status = "parsed"
    db.add(doc)
    db.commit()

    return DocumentProcessResponse(
        document_id=doc.id,
        status=doc.status,
        pages_processed=len(pages_text),
        total_chars=total_chars,
    )


@router.post("/{document_id}/index", response_model=DocumentIndexResponse)
def index_document(document_id: str, db: Session = Depends(get_db)) -> DocumentIndexResponse:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number.asc())
        .all()
    )
    if not pages:
        raise HTTPException(status_code=409, detail="Document has no parsed pages. Run /process first.")

    try:
        chunks_indexed = index_document_pages_to_weaviate(
            document_id=document_id,
            filename=doc.filename,
            content_type=doc.content_type,
            pages=pages,
        )
    except Exception as e:
        doc.status = "index_error"
        db.add(doc)
        db.commit()
        raise HTTPException(status_code=502, detail=f"Indexing failed: {e!s}") from e

    doc.status = "indexed"
    db.add(doc)
    db.commit()

    return DocumentIndexResponse(
        document_id=document_id,
        status=doc.status,
        chunks_indexed=chunks_indexed,
        pages_indexed=len(pages),
    )


# ... existing endpoints list_document_pages, get_document_page, file endpoints remain unchanged ...