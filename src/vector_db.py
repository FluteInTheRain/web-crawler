"""
Shared Qdrant Cloud client + helpers.

Both the ingestion pipeline and the RAG engine import from here.
Embeddings are generated locally with sentence-transformers; only vectors
(not raw text) are sent to Qdrant, so the free 1 GB cluster goes a long way.
"""

import uuid
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

from config import COLLECTION_NAME, EMBEDDING_MODEL, QDRANT_API_KEY, QDRANT_URL

# Embedding dimensions per model name
_DIMS: dict[str, int] = {
    "all-MiniLM-L6-v2": 384,
    "all-mpnet-base-v2": 768,
}


@lru_cache(maxsize=1)
def _encoder() -> SentenceTransformer:
    """Load (and cache) the sentence-transformer model."""
    return SentenceTransformer(EMBEDDING_MODEL)


def _client() -> QdrantClient:
    """Create a Qdrant client from config / env-vars."""
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


def _str_to_uuid(s: str) -> str:
    """Deterministically map an arbitrary string to a UUID string."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, s))


def _vector_size() -> int:
    return _DIMS.get(EMBEDDING_MODEL, 384)


def ensure_collection() -> None:
    """Create the Qdrant collection if it does not already exist."""
    client = _client()
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=_vector_size(), distance=Distance.COSINE),
        )


def upsert_chunks(
    chunk_ids: list[str],
    documents: list[str],
    payloads: list[dict],
    batch_size: int = 64,
) -> None:
    """
    Encode *documents* locally and upsert the resulting vectors into Qdrant.

    :param chunk_ids:  Unique string IDs for each chunk.
    :param documents:  Raw text of each chunk.
    :param payloads:   Metadata dicts stored alongside each vector in Qdrant
                       (should include ``page_id``, ``url``, ``title``, etc.).
    :param batch_size: Number of points uploaded per HTTP request.
    """
    ensure_collection()
    client = _client()
    encoder = _encoder()

    vectors = encoder.encode(documents, show_progress_bar=True, batch_size=32).tolist()

    points = [
        PointStruct(
            id=_str_to_uuid(uid),
            vector=vec,
            payload={**meta, "content": doc},
        )
        for uid, vec, doc, meta in zip(chunk_ids, vectors, documents, payloads)
    ]

    for i in range(0, len(points), batch_size):
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points[i : i + batch_size],
            wait=True,
        )


def search(query_text: str, n_results: int = 4) -> list[dict]:
    """
    Encode *query_text* and retrieve the top-*n_results* matching chunks.

    :param query_text: The user's natural-language question.
    :param n_results:  Number of results to return.
    :returns: List of dicts with keys ``content``, ``page_id``, ``url``,
              ``title``, ``score``.
    """
    client = _client()
    encoder = _encoder()
    query_vector = encoder.encode([query_text])[0].tolist()

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=n_results,
        with_payload=True,
    )

    return [
        {
            "content": h.payload.get("content", ""),
            "page_id": h.payload.get("page_id", ""),
            "url": h.payload.get("url", "Unknown"),
            "title": h.payload.get("title", "Unknown"),
            "score": h.score,
        }
        for h in results.points
    ]
