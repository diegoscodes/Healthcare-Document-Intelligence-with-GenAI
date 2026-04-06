from __future__ import annotations

from typing import Any

from weaviate.classes.query import Filter

from app.services.embeddings import get_embeddings
from app.services.weaviate_client import get_weaviate_client


def _distance_to_similarity(distance: float | None) -> float | None:
    if distance is None:
        return None
    d = float(distance)
    if d < 0:
        return None
    return 1.0 / (1.0 + d)


def retrieve_document_chunks(*, document_id: str, query: str, top_k: int) -> list[dict[str, Any]]:
    """
    Returns list of dicts:
      {document_id, page_number, chunk_index, text, similarity}
    """
    embeddings = get_embeddings()
    client = get_weaviate_client()
    try:
        collection = client.collections.get("DocumentChunk")
        query_vector = embeddings.embed_query(query)

        result = collection.query.near_vector(
            near_vector=query_vector,
            limit=top_k,
            filters=Filter.by_property("document_id").equal(document_id),
            return_metadata=["distance"],
            return_properties=["document_id", "page_number", "chunk_index", "text"],
        )

        items: list[dict[str, Any]] = []
        for obj in result.objects:
            props = obj.properties or {}
            distance = getattr(obj.metadata, "distance", None)
            items.append(
                {
                    "document_id": props.get("document_id"),
                    "page_number": props.get("page_number"),
                    "chunk_index": props.get("chunk_index"),
                    "text": (props.get("text") or "").strip(),
                    "similarity": _distance_to_similarity(distance),
                }
            )

        # Remove empties
        return [it for it in items if it.get("text")]
    finally:
        client.close()