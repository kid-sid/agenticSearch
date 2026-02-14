"""
Embedding client for generating text embeddings via OpenAI API.
Used by VectorSearchTool to embed code chunks and queries for FAISS indexing.
"""

import os
import numpy as np
from typing import List
from openai import OpenAI


class EmbeddingClient:
    """Generates text embeddings using OpenAI's text-embedding-3-small model."""

    MODEL = "text-embedding-3-small"
    DIMENSIONS = 1536
    MAX_BATCH_SIZE = 100  # OpenAI batch limit
    MAX_TEXT_LENGTH = 8000  # Approx safe token limit per text (chars)

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY is required for embeddings. "
                "Set it in your .env file or pass it directly."
            )
        self.client = OpenAI(api_key=self.api_key)

    def embed(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            NumPy array of shape (len(texts), DIMENSIONS) with L2-normalized vectors.
        """
        if not texts:
            return np.empty((0, self.DIMENSIONS), dtype=np.float32)

        all_embeddings = []

        for i in range(0, len(texts), self.MAX_BATCH_SIZE):
            batch = texts[i : i + self.MAX_BATCH_SIZE]

            # Truncate overly long texts
            batch = [t[:self.MAX_TEXT_LENGTH] if len(t) > self.MAX_TEXT_LENGTH else t for t in batch]

            # Replace empty strings to avoid API errors
            batch = [t if t.strip() else " " for t in batch]

            response = self.client.embeddings.create(
                model=self.MODEL,
                input=batch,
            )

            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)

        vectors = np.array(all_embeddings, dtype=np.float32)

        # L2-normalize for cosine similarity via inner product
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1  # Avoid division by zero
        vectors = vectors / norms

        return vectors

    def embed_query(self, query: str) -> np.ndarray:
        """
        Embed a single query string.

        Returns:
            NumPy array of shape (1, DIMENSIONS), L2-normalized.
        """
        return self.embed([query])
