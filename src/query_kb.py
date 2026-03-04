import chromadb
from chromadb.utils import embedding_functions

client = chromadb.PersistentClient(path="./chroma_storage")
huggingface_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)
collection = client.get_collection(
    name="ai_knowledge_base", embedding_function=huggingface_ef
)

# Test Query
query = "How can I make money from a community website?"

results = collection.query(
    query_texts=[query], n_results=3  # Get the top 3 most relevant chunks
)

for i, doc in enumerate(results["documents"][0]):
    print(f"\n--- Result {i+1} (Score: {results['distances'][0][i]}) ---")
    print(doc)
