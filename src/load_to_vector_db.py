"""
Load (or refresh) knowledge-base chunks in Qdrant Cloud.

Uses ``upsert`` so it is safe to re-run after every crawl — only new or
changed chunks are written; unchanged ones are left untouched.

Crucially, ``url`` and ``title`` are embedded in every Qdrant payload so
the query API on Render never needs access to the local metadata.json file.
"""

import json
from pathlib import Path

from config import KB_JSON_PATH, PAGES_DIR
from src.vector_db import upsert_chunks


def load_to_vector_db(
    kb_json_path: Path = KB_JSON_PATH,
    metadata_path: Path | None = None,
) -> int:
    """
    Read chunks from *kb_json_path* and upsert them into Qdrant.

    Page ``url`` and ``title`` are looked up from *metadata_path* and stored
    inside each Qdrant payload so the cloud query service is fully
    self-contained — no local files needed at query time.

    :param kb_json_path:  Path to the knowledge-base JSON produced by the chunker.
    :param metadata_path: Path to the crawler metadata index
                          (defaults to ``PAGES_DIR/metadata.json``).
    :returns: Number of chunks upserted.
    """
    if metadata_path is None:
        metadata_path = PAGES_DIR / "metadata.json"

    # page_id → {url, title} lookup
    raw_meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    meta_lookup: dict[str, dict] = {m["id"]: m for m in raw_meta}

    chunks = json.loads(kb_json_path.read_text(encoding="utf-8"))
    print(f"Loading {len(chunks)} chunks into Qdrant...")

    ids = [c["chunk_id"] for c in chunks]
    documents = [c["content"] for c in chunks]
    payloads = [
        {
            "page_id": c["page_id"],
            "chunk_index": c["chunk_index"],
            "token_count": c["token_count"],
            # Embed source info directly so Render never needs the local file
            "url": meta_lookup.get(c["page_id"], {}).get("url", "Unknown"),
            "title": meta_lookup.get(c["page_id"], {}).get("title", "Unknown"),
        }
        for c in chunks
    ]

    upsert_chunks(ids, documents, payloads)
    print(f"Qdrant updated — {len(chunks)} chunks upserted.")
    return len(chunks)


if __name__ == "__main__":
    load_to_vector_db()
