from __future__ import annotations

import os

import weaviate
from dotenv import load_dotenv


def get_weaviate_client():
    """
    Creates a Weaviate Cloud client.
    Caller must close it (client.close()).
    """
    load_dotenv()

    weaviate_url = os.getenv("WEAVIATE_URL")
    weaviate_api_key = os.getenv("WEAVIATE_API_KEY")

    if not weaviate_url:
        raise RuntimeError("WEAVIATE_URL is not set")
    if not weaviate_api_key:
        raise RuntimeError("WEAVIATE_API_KEY is not set")

    return weaviate.connect_to_weaviate_cloud(
        cluster_url=weaviate_url,
        auth_credentials=weaviate.auth.AuthApiKey(weaviate_api_key),
    )


def weaviate_is_ready() -> bool:
    client = get_weaviate_client()
    try:
        return bool(client.is_ready())
    finally:
        client.close()