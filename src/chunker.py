import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.utils.chunk_utils import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MIN_CHUNK_SIZE,
    DEFAULT_MODEL_ID,
    chunk_text,
    load_tokenizer,
)
from src.utils.text_utils import clean_markdown


# ---------------------------------------------------------------------------
# Metadata / file I/O helpers
# ---------------------------------------------------------------------------


def load_metadata(metadata_path: Path) -> List[Dict]:
    """
    Load a metadata.json index produced by the crawler.

    :param metadata_path: Path to the metadata.json file.
    :returns: List of page metadata dicts.
    """
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def load_page_text(pages_dir: Path, filename: str) -> Optional[str]:
    """
    Read the Markdown file for a single page.

    :param pages_dir: Directory that contains the page Markdown files.
    :param filename: Filename from the metadata entry.
    :returns: File text, or None when the file does not exist.
    """
    file_path = pages_dir / filename
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8")


def is_valid_entry(entry) -> bool:
    """
    Return True when a metadata entry is a successfully crawled page with a filename.

    :param entry: A single item from the metadata list.
    :returns: True if the entry is processable, False otherwise.
    """
    return (
        isinstance(entry, dict)
        and entry.get("status") == "success"
        and bool(entry.get("filename"))
    )


def process_entry(
    entry: Dict,
    pages_dir: Path,
    tokenizer,
    chunk_size: int,
    chunk_overlap: int,
    min_chunk_size: int,
    strip_images: bool,
    strip_links: bool,
) -> Tuple[List[Dict], bool]:
    """
    Clean, tokenize, and chunk a single metadata entry.

    :param entry: Metadata dict for one page.
    :param pages_dir: Directory containing page Markdown files.
    :param tokenizer: HuggingFace tokenizer instance.
    :param chunk_size: Maximum tokens per chunk.
    :param chunk_overlap: Overlap between consecutive chunks.
    :param min_chunk_size: Minimum tokens required to keep a chunk.
    :param strip_images: Pass-through for clean_markdown().
    :param strip_links: Pass-through for clean_markdown().
    :returns: Tuple of (chunks list, success flag).
              The success flag is False when the file could not be read.
    """
    raw_text = load_page_text(pages_dir, entry["filename"])
    if raw_text is None:
        return [], False

    clean_text = clean_markdown(
        raw_text, strip_images=strip_images, strip_links=strip_links
    )
    chunks = chunk_text(
        clean_text,
        page_id=entry.get("id", ""),
        tokenizer=tokenizer,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        min_chunk_size=min_chunk_size,
    )
    return chunks, True


def save_chunks(chunks: List[Dict], output_path: Path) -> None:
    """
    Write the chunk list to a JSON file.

    :param chunks: List of chunk dicts to persist.
    :param output_path: Destination file path.
    """
    output_path.write_text(
        json.dumps(chunks, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Main knowledge-base builder
# ---------------------------------------------------------------------------


def build_knowledge_base(
    metadata_path: Path = Path("pages/metadata.json"),
    pages_dir: Path = Path("pages"),
    output_path: Path = Path("ai_knowledge_base.json"),
    model_id: str = DEFAULT_MODEL_ID,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    min_chunk_size: int = DEFAULT_MIN_CHUNK_SIZE,
    strip_images: bool = True,
    strip_links: bool = True,
) -> List[Dict]:
    """
    Build a knowledge base from crawled Markdown pages.

    Reads the metadata index, cleans and chunks each successfully crawled page,
    then writes all chunks to a single JSON file.

    :param metadata_path: Path to the crawler's metadata.json index.
    :param pages_dir: Directory containing page Markdown files.
    :param output_path: Destination path for the output JSON.
    :param model_id: HuggingFace model ID for the tokenizer.
    :param chunk_size: Maximum tokens per chunk.
    :param chunk_overlap: Token overlap between consecutive chunks.
    :param min_chunk_size: Minimum tokens to keep a chunk (except the first).
    :param strip_images: Remove Markdown image syntax before chunking.
    :param strip_links: Collapse Markdown link syntax to label text.
    :returns: List of all chunk dicts written to disk.
    """
    tokenizer = load_tokenizer(model_id)
    metadata = load_metadata(metadata_path)

    all_chunks: List[Dict] = []
    processed = 0
    skipped = 0

    for entry in metadata:
        if not is_valid_entry(entry):
            skipped += 1
            continue

        chunks, success = process_entry(
            entry,
            pages_dir,
            tokenizer,
            chunk_size,
            chunk_overlap,
            min_chunk_size,
            strip_images,
            strip_links,
        )
        if not success:
            skipped += 1
            continue

        all_chunks.extend(chunks)
        processed += 1

    save_chunks(all_chunks, output_path)
    print(
        f"Processed {processed} files (skipped {skipped}) "
        f"into {len(all_chunks)} chunks."
    )
    return all_chunks


if __name__ == "__main__":
    build_knowledge_base()
