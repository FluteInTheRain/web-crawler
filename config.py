"""
Project-wide configuration.

All values can be overridden via a .env file (loaded automatically) or by
setting real environment variables.  CLI flags passed at runtime take the
highest precedence and shadow these defaults.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Target website
# ---------------------------------------------------------------------------
TARGET_URL: str = os.getenv("TARGET_URL", "https://sharetribe.com")

# ---------------------------------------------------------------------------
# Storage paths
# ---------------------------------------------------------------------------
PAGES_DIR: Path = Path(os.getenv("PAGES_DIR", "out_md"))
KB_JSON_PATH: Path = Path(os.getenv("KB_JSON_PATH", "kb.json"))
COLLECTION_NAME: str = os.getenv("COLLECTION_NAME", "ai_knowledge_base")

# ---------------------------------------------------------------------------
# Crawler
# ---------------------------------------------------------------------------
CONCURRENCY: int = int(os.getenv("CONCURRENCY", "5"))
_max_pages_raw = os.getenv("MAX_PAGES")
MAX_PAGES: int | None = int(_max_pages_raw) if _max_pages_raw else None

# ---------------------------------------------------------------------------
# Embedding model (used for both the chunker tokeniser and ChromaDB)
# ---------------------------------------------------------------------------
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# ---------------------------------------------------------------------------
# Qdrant Cloud (vector database)
# ---------------------------------------------------------------------------
QDRANT_URL: str = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")

# ---------------------------------------------------------------------------
# LLM (OpenAI)
# ---------------------------------------------------------------------------
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o")
