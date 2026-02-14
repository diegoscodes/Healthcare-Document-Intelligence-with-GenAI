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
)
from app.services.document_loader import extract_pdf_pages_text

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


@router.get(
    "/{document_id}/pages",
    response_model=DocumentPagesReadResponse,
    responses={
        404: {
            "description": "Document not found",
            "content": {"application/json": {"example": {"detail": "Document not found"}}},
        }
    },
)
def list_document_pages(
    document_id: str,
    include_text: bool = True,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> DocumentPagesReadResponse:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset must be >= 0")

    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    pages_query = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number.asc())
    )

    pages_count = pages_query.count()
    pages = pages_query.offset(offset).limit(limit).all()

    total_chars = (
        db.query(func.coalesce(func.sum(func.length(DocumentPage.text)), 0))
        .filter(DocumentPage.document_id == document_id)
        .scalar()
    )

    return DocumentPagesReadResponse(
        document_id=document_id,
        pages=[
            DocumentPageReadResponse(
                document_id=p.document_id,
                page_number=p.page_number,
                text=p.text if include_text else None,
            )
            for p in pages
        ],
        pages_count=pages_count,
        total_chars=int(total_chars or 0),
    )


@router.get(
    "/{document_id}/pages/{page_number}",
    response_model=DocumentPageReadResponse,
    responses={
        404: {
            "description": "Document or page not found",
            "content": {
                "application/json": {
                    "examples": {
                        "document_not_found": {"value": {"detail": "Document not found"}},
                        "page_not_found": {"value": {"detail": "Page not found"}},
                    }
                }
            },
        }
    },
)
def get_document_page(document_id: str, page_number: int, db: Session = Depends(get_db)) -> DocumentPageReadResponse:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    page = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document_id, DocumentPage.page_number == page_number)
        .one_or_none()
    )
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")

    return DocumentPageReadResponse(
        document_id=page.document_id,
        page_number=page.page_number,
        text=page.text,
    )