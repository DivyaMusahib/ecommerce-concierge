"""
FAQ Retrieval Tool - Real RAG with FAISS + Gemini Embeddings.

Uses Gemini's API for embeddings to save RAM (ideal for free hosting tiers).
FAISS index is built from faq.md on first run and persisted to disk.
"""
import os
from langchain_core.tools import tool
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document

# Paths
_DIR = os.path.dirname(__file__)
_FAQ_PATH = os.path.join(_DIR, "..", "..", "data", "faq.md")
_INDEX_PATH = os.path.join(_DIR, "..", "..", "data", "faq_faiss_index_gemini")

# Gemini embeddings
_EMBEDDING_MODEL = "models/text-embedding-005"

vector_store = None
_embeddings = None


def _get_embeddings() -> GoogleGenerativeAIEmbeddings:
    """Lazy-load the Gemini embeddings model."""
    global _embeddings
    if _embeddings is None:
        from app.core.config import settings
        print(f"[FAQ RAG] Loading Gemini embeddings model: {_EMBEDDING_MODEL}")
        _embeddings = GoogleGenerativeAIEmbeddings(
            model=_EMBEDDING_MODEL,
            google_api_key=settings.GEMINI_API_KEY
        )
        print("[FAQ RAG] Embeddings model ready.")
    return _embeddings


def _build_docs() -> list[Document]:
    """Parse faq.md into LangChain Documents split by ## section headers."""
    with open(_FAQ_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    docs = []
    for chunk in content.split("## ")[1:]:
        lines = chunk.strip().split("\n", 1)
        title = lines[0].strip()
        text = lines[1].strip() if len(lines) == 2 else ""
        docs.append(Document(
            page_content=f"Policy: {title}\nDetails: {text}",
            metadata={"topic": title},
        ))
    return docs


def _get_vector_store() -> FAISS | None:
    """Load from disk or build + save the FAISS vector store."""
    global vector_store
    if vector_store is not None:
        return vector_store

    if not os.path.exists(_FAQ_PATH):
        print("[FAQ RAG] faq.md not found.")
        return None

    embeddings = _get_embeddings()

    # Try loading persisted index first
    if os.path.exists(_INDEX_PATH):
        try:
            vector_store = FAISS.load_local(
                _INDEX_PATH,
                embeddings,
                allow_dangerous_deserialization=True,
            )
            print("[FAQ RAG] Loaded FAISS index from disk.")
            return vector_store
        except Exception as e:
            print(f"[FAQ RAG] Disk load failed ({e}), rebuilding...")

    # Build from scratch and persist
    docs = _build_docs()
    if not docs:
        return None

    vector_store = FAISS.from_documents(docs, embeddings)
    vector_store.save_local(_INDEX_PATH)
    print(f"[FAQ RAG] Built and persisted FAISS index ({len(docs)} chunks) using {_EMBEDDING_MODEL}.")
    return vector_store


@tool
def search_faq(query: str) -> str:
    """Search the company FAQ knowledge base using semantic vector search (RAG). Handles returns, shipping, warranty, payments, and all company policies."""
    vs = _get_vector_store()
    if not vs:
        return _keyword_fallback(query)

    # Retrieve top 2 most semantically similar policy chunks
    results = vs.similarity_search(query, k=2)
    if results:
        return "\n\n---\n\n".join(doc.page_content for doc in results)
    return "No relevant FAQ entry found for your query."


def _keyword_fallback(query: str) -> str:
    """Simple keyword fallback if vector store is unavailable."""
    if not os.path.exists(_FAQ_PATH):
        return "FAQ knowledge base is currently unavailable."

    with open(_FAQ_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    query_words = set(query.lower().split())
    best, max_score = None, 0
    for chunk in content.split("## ")[1:]:
        score = len(query_words & set(chunk.lower().split()))
        if score > max_score:
            max_score, best = score, chunk.strip()

    return best if (best and max_score > 0) else "No relevant FAQ entry found."
