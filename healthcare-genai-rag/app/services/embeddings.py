from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings


def get_embeddings() -> OpenAIEmbeddings:
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_EMBEDDINGS_MODEL")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    if not model:
        raise RuntimeError("OPENAI_EMBEDDINGS_MODEL is not set")

    return OpenAIEmbeddings(
        model=model,
        api_key=api_key,
    )