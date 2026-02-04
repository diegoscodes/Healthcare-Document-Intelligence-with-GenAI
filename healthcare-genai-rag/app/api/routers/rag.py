from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/rag", tags=["rag"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}