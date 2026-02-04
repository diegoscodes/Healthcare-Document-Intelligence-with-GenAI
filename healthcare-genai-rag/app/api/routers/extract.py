from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/extract", tags=["extract"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}