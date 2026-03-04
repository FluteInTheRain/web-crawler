import uuid
from typing import Dict, List

from transformers import AutoTokenizer

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

DEFAULT_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 80
DEFAULT_MIN_CHUNK_SIZE = 100


def load_tokenizer(model_id: str = DEFAULT_MODEL_ID):
    """
    Load and return a HuggingFace tokenizer for the given model.

    :param model_id: HuggingFace model identifier.
    :returns: Loaded AutoTokenizer instance.
    """
    return AutoTokenizer.from_pretrained(model_id)


def tokenize(text: str, tokenizer) -> List[int]:
    """
    Encode text into a list of token IDs using the given tokenizer.

    :param text: Input text to tokenize.
    :param tokenizer: HuggingFace tokenizer instance.
    :returns: List of integer token IDs (without special tokens).
    """
    return tokenizer.encode(text, add_special_tokens=False)


def decode_tokens(token_ids: List[int], tokenizer) -> str:
    """
    Decode a list of token IDs back into a string.

    :param token_ids: List of integer token IDs.
    :param tokenizer: HuggingFace tokenizer instance.
    :returns: Decoded text string.
    """
    return tokenizer.decode(token_ids, skip_special_tokens=True)


def build_chunk_record(
    content: str,
    page_id: str,
    chunk_index: int,
    token_count: int,
) -> Dict:
    """
    Create a structured chunk dict ready for storage.

    :param content: Decoded text content of this chunk.
    :param page_id: Identifier of the source page.
    :param chunk_index: Zero-based position of this chunk within the page.
    :param token_count: Number of tokens in this chunk.
    :returns: Dict with keys: chunk_id, page_id, chunk_index, content, token_count.
    """
    return {
        "chunk_id": str(uuid.uuid4()),
        "page_id": page_id,
        "chunk_index": chunk_index,
        "content": content,
        "token_count": token_count,
    }


def chunk_tokens(
    tokens: List[int],
    page_id: str,
    tokenizer,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    min_chunk_size: int = DEFAULT_MIN_CHUNK_SIZE,
) -> List[Dict]:
    """
    Split a flat list of token IDs into overlapping chunks.

    :param tokens: Full token ID list for a page.
    :param page_id: Identifier of the source page.
    :param tokenizer: HuggingFace tokenizer used for decoding.
    :param chunk_size: Maximum tokens per chunk.
    :param chunk_overlap: Number of tokens to repeat at the start of each
                          subsequent chunk for context continuity.
    :param min_chunk_size: Chunks smaller than this are discarded (except the
                           first chunk of a page, which is always kept).
    :returns: List of chunk dicts.
    """
    chunks: List[Dict] = []
    start = 0

    while start < len(tokens):
        end = start + chunk_size
        chunk_token_ids = tokens[start:end]
        token_count = len(chunk_token_ids)

        if token_count >= min_chunk_size or start == 0:
            content = decode_tokens(chunk_token_ids, tokenizer)
            chunks.append(
                build_chunk_record(content, page_id, len(chunks), token_count)
            )

        if end >= len(tokens):
            break
        start += chunk_size - chunk_overlap

    return chunks


def chunk_text(
    text: str,
    page_id: str,
    tokenizer,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    min_chunk_size: int = DEFAULT_MIN_CHUNK_SIZE,
) -> List[Dict]:
    """
    Tokenize *text* and split it into overlapping chunks.

    Convenience wrapper around tokenize() + chunk_tokens().

    :param text: Plain text or Markdown content to chunk.
    :param page_id: Identifier of the source page.
    :param tokenizer: HuggingFace tokenizer instance.
    :param chunk_size: Maximum tokens per chunk.
    :param chunk_overlap: Overlap between consecutive chunks in tokens.
    :param min_chunk_size: Minimum tokens required to keep a chunk.
    :returns: List of chunk dicts.
    """
    tokens = tokenize(text, tokenizer)
    return chunk_tokens(
        tokens, page_id, tokenizer, chunk_size, chunk_overlap, min_chunk_size
    )
