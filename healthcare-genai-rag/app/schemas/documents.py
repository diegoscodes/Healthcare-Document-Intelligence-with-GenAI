from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DocumentCreateRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)


class DocumentCreateResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    content_type: str


class DocumentReadResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    content_type: str
    created_at: datetime

class DocumentProcessResponse(BaseModel):
    document_id: str
    status: str
    pages_processed: int
    total_chars: int


class DocumentPageReadResponse(BaseModel):
    document_id: str
    page_number: int
    text: str | None = None


class DocumentPagesReadResponse(BaseModel):
    document_id: str
    pages: list[DocumentPageReadResponse]
    pages_count: int
    total_chars: int