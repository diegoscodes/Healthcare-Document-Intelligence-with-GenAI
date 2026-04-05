from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.rag import RagExtractRequest, RagExtractResponse
from app.services.rag_pipeline import extract_structured_json

router = APIRouter(prefix="/rag", tags=["rag"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/extract", response_model=RagExtractResponse)
def extract(req: RagExtractRequest) -> RagExtractResponse:
    try:
        return extract_structured_json(
            document_id=req.document_id,
            query=req.query,
            top_k=req.top_k,
            max_evidence=req.max_evidence,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"RAG extraction failed: {e!s}") from e