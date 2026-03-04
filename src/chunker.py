import json
import uuid
from pathlib import Path
from transformers import AutoTokenizer

# 1. Configuration - Choosing a standard RAG-friendly tokenizer
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

CHUNK_SIZE = 800
CHUNK_OVERLAP = 80  # 10% overlap for context continuity
INPUT_METADATA = "pages/metadata.json"
OUTPUT_CHUNKS = "./kb_chunks.json"


def create_chunks(text, page_id):
    # Encode the text into token IDs
    tokens = tokenizer.encode(text, add_special_tokens=False)

    chunks = []
    chunk_index = 0

    # Sliding window logic
    for i in range(0, len(tokens), CHUNK_SIZE - CHUNK_OVERLAP):
        # Extract the window of tokens
        chunk_tokens = tokens[i : i + CHUNK_SIZE]

        # Decode back to text (cleaning up special characters)
        chunk_content = tokenizer.decode(chunk_tokens, skip_special_tokens=True)

        chunks.append(
            {
                "chunk_id": str(uuid.uuid4()),
                "page_id": page_id,
                "chunk_index": chunk_index,
                "content": chunk_content,
                "token_count": len(chunk_tokens),
            }
        )

        chunk_index += 1

        # Stop if we've reached the end of the tokens
        if i + CHUNK_SIZE >= len(tokens):
            break

    return chunks


def run_pipeline():
    with open(INPUT_METADATA, "r") as f:
        pages = json.load(f)

    all_chunks = []

    # Only process pages that were successfully crawled and have a file
    valid_pages = [
        p for p in pages if p.get("status") == "success" and p.get("filename")
    ]
    skipped = len(pages) - len(valid_pages)
    if skipped:
        print(f"⚠️  Skipping {skipped} page(s) with errors or missing content.")
    print(f"Starting transformation of {len(valid_pages)} pages...")

    for page in valid_pages:
        # filenames in metadata are stored relative to the `pages/` directory
        file_path = Path("pages") / Path(page["filename"])
        if not file_path.exists():
            print(f"⚠️ Warning: {page['filename']} not found. Skipping.")
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Transform Page -> Multiple Chunks
        page_chunks = create_chunks(content, page["id"])
        all_chunks.extend(page_chunks)

    # Save the new AI Knowledge Base
    with open(OUTPUT_CHUNKS, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)

    print(f"Success! Created {len(all_chunks)} chunks from {len(valid_pages)} pages.")


if __name__ == "__main__":
    run_pipeline()
