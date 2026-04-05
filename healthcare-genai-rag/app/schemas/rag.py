from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RagExtractRequest(BaseModel):
    document_id: str = Field(min_length=1)
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=6, ge=1, le=20)
    max_evidence: int = Field(default=5, ge=1, le=20)


class Medication(BaseModel):
    name: str = ""
    dose: str = ""
    frequency: str = ""


Decision = Literal["approved", "denied", "pending", "unknown", ""]


class PriorAuthExtraction(BaseModel):
    patient_name: str = ""

    patient_id: str = ""
    member_id: str = ""
    member_group: str = ""

    dob: str = ""

    service_date: str = ""
    admission_date: str = ""
    authorization_period_start: str = ""
    authorization_period_end: str = ""

    diagnosis: str = ""
    icd10_codes: list[str] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)
    provider: str = ""
    decision: Decision = "unknown"
    rationale: str = ""


class Evidence(BaseModel):
    document_id: str
    page_number: int | None = None
    chunk_index: int | None = None
    snippet: str = Field(min_length=1, max_length=2000)
    similarity: float | None = Field(default=None, ge=0.0, le=1.0)


class RagExtractResponse(BaseModel):
    document_id: str
    query: str
    extracted: PriorAuthExtraction
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)