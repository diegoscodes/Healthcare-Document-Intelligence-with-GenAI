from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AgenticQARequest(BaseModel):
    document_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=30)
    max_context_chars: int = Field(default=8000, ge=500, le=30000)
    retries: int = Field(default=1, ge=0, le=2)
    allow_insufficient: bool = Field(default=True)


class Citation(BaseModel):
    document_id: str
    page_number: int | None = None
    chunk_index: int | None = None
    similarity: float | None = Field(default=None, ge=0.0, le=1.0)


class RetrievedChunk(BaseModel):
    document_id: str
    page_number: int | None = None
    chunk_index: int | None = None
    text: str = Field(min_length=1)
    similarity: float | None = Field(default=None, ge=0.0, le=1.0)


class PlanStep(BaseModel):
    name: str
    query: str | None = None


class AgenticQAPlan(BaseModel):
    strategy: Literal["single_query", "multi_query"] = "multi_query"
    steps: list[PlanStep] = Field(default_factory=list)


class VerificationResult(BaseModel):
    ok: bool
    issues: list[str] = Field(default_factory=list)


class WorkflowStep(BaseModel):
    name: str
    meta: dict[str, object] = Field(default_factory=dict)


class LLMStructuredCitation(BaseModel):
    page_number: int = Field(ge=1)
    chunk_index: int = Field(ge=1)


class LLMStructuredAnswer(BaseModel):
    answer: str = Field(min_length=1)
    citations: list[LLMStructuredCitation] = Field(default_factory=list)


class AgenticQAResponse(BaseModel):
    document_id: str
    question: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    verification: VerificationResult
    retrieved: list[RetrievedChunk] = Field(default_factory=list)
    plan: AgenticQAPlan | None = None
    steps: list[WorkflowStep] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)