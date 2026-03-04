import json
import chromadb
from chromadb.utils import embedding_functions

# 1. Setup Persistence
# This creates a folder 'chroma_storage' where your data actually lives.
client = chromadb.PersistentClient(path="./chroma_storage")

# 2. Define the Embedding Function
# We use the same model as your tokenizer to ensure semantic alignment.
huggingface_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

# 3. Get or Create the Collection
collection = client.get_or_create_collection(
    name="ai_knowledge_base",
    embedding_function=huggingface_ef,
    metadata={"hnsw:space": "cosine"},  # Use cosine similarity for better text matching
)


def load_to_vector_db():
    with open("kb.json", "r") as f:
        chunks = json.load(f)

    print(f"📦 Loading {len(chunks)} chunks into ChromaDB...")

    # We batch the uploads for better performance
    ids = [c["chunk_id"] for c in chunks]
    documents = [c["content"] for c in chunks]
    metadatas = [
        {
            "page_id": c["page_id"],
            "index": c["chunk_index"],
            "token_count": c["token_count"],
        }
        for c in chunks
    ]

    # Chroma handles the embedding generation automatically here
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    print("✅ Vector Database is ready!")


if __name__ == "__main__":
    load_to_vector_db()
