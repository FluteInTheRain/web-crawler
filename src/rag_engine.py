"""
RAG engine — retrieve chunks from Qdrant and generate answers via OpenAI.

Public API
----------
create_rag_engine(n_results, model) -> Callable[[str, int], dict]
    Returns an ``answer(question, n_results)`` callable.
    Result dict::

        {
            "answer":  "<cited answer text>",
            "sources": [{"title": "...", "url": "..."}, ...]
        }

No local files are needed at query time — url/title come from the Qdrant
payload, making the Render deployment fully self-contained.
"""

import os

from openai import OpenAI

from config import LLM_MODEL, OPENAI_API_KEY
from src.vector_db import search as vector_search


def create_rag_engine(n_results: int = 4, model: str | None = None):
    """
    Build and return a question-answering callable.

    :param n_results: Default number of chunks to retrieve per question.
    :param model: OpenAI model; falls back to ``LLM_MODEL`` from config.
    :returns: ``answer(question, n_results) -> dict`` callable.
    """
    api_key = OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. "
            "Add it to your .env file or export it as an environment variable."
        )

    llm_model = model or LLM_MODEL
    ai_client = OpenAI(api_key=api_key)

    def answer(user_query: str, n_results: int = n_results) -> dict:
        """
        Retrieve relevant chunks from Qdrant and generate a cited answer.

        :param user_query: The user's natural-language question.
        :param n_results:  Number of chunks to retrieve (overrides the default).
        :returns: Dict with ``answer`` (str) and ``sources`` (list of dicts).
        """
        # 1. Semantic retrieval — url/title come from the Qdrant payload
        hits = vector_search(user_query, n_results=n_results)

        # 2. Build context + source list
        context_str = ""
        sources: list[dict] = []
        for i, hit in enumerate(hits):
            sid = i + 1
            sources.append({"title": hit["title"], "url": hit["url"]})
            context_str += (
                f"\nSource [{sid}] (Title: {hit['title']}):\n{hit['content']}\n"
            )

        # 3. Prompt
        system_prompt = (
            "You are a professional researcher. "
            "Use the [CONTEXT] to answer the user's question.\n"
            "CRITICAL RULE: You MUST cite your sources using square brackets, "
            "e.g. [1] or [1][3]. Place citations at the end of the sentences "
            "they support. If the context doesn't contain the answer, say so."
        )
        user_prompt = f"[CONTEXT]{context_str}\n\n[QUESTION]{user_query}"

        # 4. Generate
        response = ai_client.chat.completions.create(
            model=llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        answer_text = response.choices[0].message.content

        # 5. Append bibliography
        answer_text += "\n\nSOURCES:"
        for idx, src in enumerate(sources, 1):
            answer_text += f"\n[{idx}] {src['title']} — {src['url']}"

        return {"answer": answer_text, "sources": sources}

    return answer
