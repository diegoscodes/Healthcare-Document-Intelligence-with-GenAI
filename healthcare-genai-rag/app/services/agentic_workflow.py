from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re

from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import Document, DocumentPage
from app.schemas.rag import RagExtractRequest, RagExtractResponse
from app.services.rag_pipeline import extract_structured_json, is_document_indexed
from app.services.vector_store import index_document_pages_to_weaviate


@dataclass(frozen=True)
class WorkflowStep:
    name: str
    meta: dict[str, Any]


class RagAgentWorkflow:
    """
    Minimal agentic workflow:
      - plan: decide which steps/tools to run
      - execute: run extraction
      - fallback: return safe response with warnings on failure
      - trace: keep an internal step list (can be logged later)
    """

    _UNSUPPORTED_QUERY_RE = re.compile(
        r"\b(phone|phone number|telephone|tel|address|home address|mailing address|street|zip|postal code)\b",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self.steps: list[WorkflowStep] = []

    def _step(self, name: str, **meta: Any) -> None:
        self.steps.append(WorkflowStep(name=name, meta=meta))

    def _unsupported_query_warning(self, query: str) -> str | None:
        q = (query or "").strip()
        if not q:
            return None
        if self._UNSUPPORTED_QUERY_RE.search(q):
            return (
                "Query asks for contact/location details (e.g., phone/address) which are not supported by the "
                "current extraction schema and may not exist in the document. Returning standard extraction instead."
            )
        return None

    def _auto_index_if_missing(self, db: Session, document_id: str) -> int:
        """
        Agent tool: ensure Weaviate has chunks for this document.
        Returns number of chunks indexed (0 if already indexed).
        """
        if is_document_indexed(document_id):
            return 0

        doc = db.get(Document, document_id)
        if doc is None:
            raise RuntimeError("Document not found")

        pages = (
            db.query(DocumentPage)
            .filter(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_number.asc())
            .all()
        )
        if not pages:
            raise RuntimeError("Document has no parsed pages. Run /documents/{document_id}/process first.")

        return index_document_pages_to_weaviate(
            document_id=document_id,
            filename=doc.filename,
            content_type=doc.content_type,
            pages=pages,
        )

    def run(self, req: RagExtractRequest) -> RagExtractResponse:
        self._step(
            "plan",
            document_id=req.document_id,
            top_k=req.top_k,
            max_evidence=req.max_evidence,
        )

        unsupported_warning = self._unsupported_query_warning(req.query)
        if unsupported_warning:
            self._step("guardrail:unsupported_query", warning=unsupported_warning)

        # Agentic remediation: index-if-missing
        db = next(get_db())
        try:
            self._step("tool:auto_index_if_missing")
            chunks_indexed = self._auto_index_if_missing(db, req.document_id)
            self._step("tool:auto_index_if_missing:done", chunks_indexed=chunks_indexed)
        finally:
            db.close()

        self._step("tool:extract_structured_json", query_len=len(req.query or ""))

        try:
            resp = extract_structured_json(
                document_id=req.document_id,
                query=req.query,
                top_k=req.top_k,
                max_evidence=req.max_evidence,
            )

            resp.warnings = list(resp.warnings or [])

            if chunks_indexed > 0:
                resp.warnings.append(f"Auto-index executed: {chunks_indexed} chunks indexed for this document.")

            if unsupported_warning and unsupported_warning not in resp.warnings:
                resp.warnings.append(unsupported_warning)

            self._step("done", warnings_count=len(resp.warnings or []))
            return resp
        except Exception as e:
            self._step("fallback", error=str(e))
            raise