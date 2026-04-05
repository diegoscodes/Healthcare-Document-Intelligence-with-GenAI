from __future__ import annotations

import os

import weaviate
from dotenv import load_dotenv

# Weaviate v4 collections API
from weaviate.classes.config import Configure, DataType, Property


def get_client():
    load_dotenv()
    url = os.getenv("WEAVIATE_URL")
    api_key = os.getenv("WEAVIATE_API_KEY")

    if not url or not api_key:
        raise RuntimeError("Missing WEAVIATE_URL or WEAVIATE_API_KEY in environment")

    return weaviate.connect_to_weaviate_cloud(
        cluster_url=url,
        auth_credentials=weaviate.auth.AuthApiKey(api_key),
    )


def ensure_document_chunk_collection() -> None:
    client = get_client()
    try:
        collections = client.collections

        if collections.exists("DocumentChunk"):
            return

        collections.create(
            name="DocumentChunk",
            vectorizer_config=Configure.Vectorizer.none(),
            properties=[
                Property(name="document_id", data_type=DataType.TEXT),
                Property(name="page_number", data_type=DataType.INT),
                Property(name="chunk_index", data_type=DataType.INT),
                Property(name="text", data_type=DataType.TEXT),

                Property(name="filename", data_type=DataType.TEXT),
                Property(name="content_type", data_type=DataType.TEXT),
                Property(name="created_at", data_type=DataType.DATE),
            ],
        )
    finally:
        client.close()


if __name__ == "__main__":
    ensure_document_chunk_collection()
    print("OK: DocumentChunk collection is ready.")