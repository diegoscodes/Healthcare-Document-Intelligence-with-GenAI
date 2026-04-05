from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.rag import RagExtractRequest, RagExtractResponse
from app.services.agentic_workflow import RagAgentWorkflow

router = APIRouter(prefix="/rag", tags=["rag"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/extract", response_model=RagExtractResponse)
def extract(req: RagExtractRequest) -> RagExtractResponse:
    workflow = RagAgentWorkflow()
    try:
        return workflow.run(req)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"RAG extraction failed: {e!s}") from e