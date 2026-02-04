from __future__ import annotations

from fastapi import FastAPI

from app.api.routers import documents, extract, rag


def create_app() -> FastAPI:
    app = FastAPI(title="Healthcare Document Intelligence with GenAI (MediRAG)")

    app.include_router(documents.router)
    app.include_router(extract.router)
    app.include_router(rag.router)

    @app.get("/health", tags=["health"])
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()