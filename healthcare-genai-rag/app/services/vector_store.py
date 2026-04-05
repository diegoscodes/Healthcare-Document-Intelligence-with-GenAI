from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.embeddings import get_embeddings
from app.services.weaviate_client import get_weaviate_client


def _split_page_text(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_text(text or "")
    return [c.strip() for c in chunks if c and c.strip()]


def index_document_pages_to_weaviate(
    document_id: str,
    filename: str,
    content_type: str,
    pages: Iterable[object],
) -> int:
    """
    Indexes parsed pages into Weaviate collection `DocumentChunk`.

    Expects each `page` to have:
      - page.page_number (int)
      - page.text (str)

    Returns: number of chunks indexed.
    """
    embeddings = get_embeddings()
    client = get_weaviate_client()

    try:
        collection = client.collections.get("DocumentChunk")

        total_chunks = 0
        created_at = datetime.now(timezone.utc).isoformat()

        with collection.batch.dynamic() as batch:
            for page in pages:
                page_number = int(getattr(page, "page_number"))
                page_text = getattr(page, "text") or ""

                chunks = _split_page_text(page_text)

                if not chunks:
                    continue

                vectors = embeddings.embed_documents(chunks)

                for chunk_index, (chunk_text, vector) in enumerate(zip(chunks, vectors), start=1):
                    batch.add_object(
                        properties={
                            "document_id": document_id,
                            "page_number": page_number,
                            "chunk_index": chunk_index,
                            "text": chunk_text,
                            "filename": filename or "",
                            "content_type": content_type or "",
                            "created_at": created_at,
                        },
                        vector=vector,
                    )
                    total_chunks += 1

        return total_chunks
    finally:
        client.close()