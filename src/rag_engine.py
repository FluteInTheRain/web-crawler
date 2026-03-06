#####

import json
import os
import chromadb
from openai import OpenAI
from chromadb.utils import embedding_functions

from dotenv import load_dotenv

load_dotenv()

# 1. Setup
client = chromadb.PersistentClient(path="./chroma_storage")
huggingface_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)
collection = client.get_collection(
    name="ai_knowledge_base", embedding_function=huggingface_ef
)
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError(
        "OPENAI_API_KEY environment variable is not set. Please set it before running the RAG engine."
    )

ai_client = OpenAI(api_key=api_key)

# Load your original metadata into a lookup table for speed
with open("out_md/metadata.json", "r") as f:
    raw_metadata = json.load(f)
    # Create a quick-access map: { "page_uuid": {"url": "...", "title": "..."} }
    metadata_lookup = {item["id"]: item for item in raw_metadata}


def get_answer_with_citations(user_query):
    # STEP 1: Semantic Retrieval
    results = collection.query(query_texts=[user_query], n_results=4)

    # STEP 2: Build the Context with Source Keys
    context_str = ""
    sources_used = {}

    for i, (doc, meta) in enumerate(
        zip(results["documents"][0], results["metadatas"][0])
    ):
        source_id = i + 1
        page_id = meta["page_id"]
        source_info = metadata_lookup.get(
            page_id, {"url": "Unknown", "title": "Unknown"}
        )

        # Store for the final reference list
        sources_used[source_id] = source_info

        # Format the context for the LLM
        context_str += (
            f"\nSource [{source_id}] (Title: {source_info['title']}):\n{doc}\n"
        )

    # STEP 3: The Prompt
    system_prompt = """
    You are a professional researcher. Use the [CONTEXT] to answer the user's question.
    CRITICAL RULE: You MUST cite your sources using square brackets, e.g., [1] or [1][3].
    Place the citations at the end of the sentences they support.
    If the context doesn't contain the answer, state that clearly.
    """

    user_prompt = f"[CONTEXT]{context_str}\n\n[QUESTION]{user_query}"

    # STEP 4: Generate
    response = ai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )

    answer = response.choices[0].message.content

    # STEP 5: Append the "Bibliography"
    answer += "\n\nSOURCES:"
    for sid, info in sources_used.items():
        answer += f"\n[{sid}] {info['title']} - {info['url']}"

    return answer


print(get_answer_with_citations("How do I build a profile page?"))
