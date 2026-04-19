"""
ChromaDB Document Manager
Add documents and run semantic search using OpenRouter + text-embedding-3-large
"""

import os
import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings
from openai import OpenAI


# ─── Embedding Function ───────────────────────────────────────────────────────

class OpenRouterEmbedding(EmbeddingFunction):
    def __init__(self, api_key: str, model: str = "openai/text-embedding-3-large"):
        self.model = model
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    def __call__(self, input: Documents) -> Embeddings:
        response = self.client.embeddings.create(
            model=self.model,
            input=input,
        )
        return [item.embedding for item in response.data]


# ─── ChromaDB Setup ───────────────────────────────────────────────────────────

def get_collection(api_key: str, persist_path: str = "./chroma_db"):
    embedding_fn = OpenRouterEmbedding(api_key=api_key)
    client = chromadb.PersistentClient(path=persist_path)
    collection = client.get_or_create_collection(
        name="documents",
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},  # cosine similarity
    )
    return collection


# ─── Add Document ─────────────────────────────────────────────────────────────

def add_document(collection, doc_id: str, text: str, metadata: dict = None):
    """
    Add a single document to the collection.

    Args:
        collection: ChromaDB collection
        doc_id:     Unique ID string (e.g. "doc_001")
        text:       The document text to embed and store
        metadata:   Optional dict of metadata (e.g. {"source": "wiki", "author": "Alice"})
    """
    collection.add(
        ids=[doc_id],
        documents=[text],
        metadatas=[metadata or {}],
    )
    print(f"[+] Added document '{doc_id}'")


def add_documents_batch(collection, docs: list[dict]):
    """
    Add multiple documents in one call.

    Each item in `docs` should be a dict with keys:
        id (str), text (str), metadata (dict, optional)

    Example:
        docs = [
            {"id": "doc_001", "text": "Python is a programming language.", "metadata": {"topic": "programming"}},
            {"id": "doc_002", "text": "The Eiffel Tower is in Paris.",     "metadata": {"topic": "geography"}},
        ]
    """
    ids       = [d["id"]               for d in docs]
    documents = [d["text"]             for d in docs]
    metadatas = [d.get("metadata", {}) for d in docs]

    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    print(f"[+] Added {len(docs)} documents")


# ─── Search / Query ───────────────────────────────────────────────────────────

def search(collection, query: str, n_results: int = 3, where: dict = None):
    """
    Semantic search over the collection.

    Args:
        collection: ChromaDB collection
        query:      Natural language search query
        n_results:  Number of results to return (default 3)
        where:      Optional metadata filter, e.g. {"topic": "programming"}

    Returns:
        List of dicts with keys: id, document, distance, metadata
    """
    kwargs = dict(
        query_texts=[query],
        n_results=n_results,
        include=["documents", "distances", "metadatas"],
    )
    if where:
        kwargs["where"] = where

    results = collection.query(**kwargs)

    hits = []
    for i in range(len(results["ids"][0])):
        hits.append({
            "id":       results["ids"][0][i],
            "document": results["documents"][0][i],
            "distance": round(results["distances"][0][i], 4),
            "metadata": results["metadatas"][0][i],
        })
    return hits


# ─── Delete / Update ──────────────────────────────────────────────────────────

def delete_document(collection, doc_id: str):
    collection.delete(ids=[doc_id])
    print(f"[-] Deleted document '{doc_id}'")


def update_document(collection, doc_id: str, new_text: str, metadata: dict = None):
    """Re-embeds and replaces an existing document."""
    collection.update(
        ids=[doc_id],
        documents=[new_text],
        metadatas=[metadata or {}],
    )
    print(f"[~] Updated document '{doc_id}'")


# ─── Demo ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    API_KEY = os.environ.get("OPENROUTER_API_KEY", "your-openrouter-api-key")

    collection = get_collection(api_key=API_KEY)

    # ── Add documents ──────────────────────────────────────────────────────────
    add_documents_batch(collection, [
        {
            "id": "doc_001",
            "text": "Python is a high-level, dynamically typed programming language known for its readability.",
            "metadata": {"topic": "programming", "language": "Python"},
        },
        {
            "id": "doc_002",
            "text": "The Eiffel Tower is a wrought-iron lattice tower in Paris, France, completed in 1889.",
            "metadata": {"topic": "geography", "country": "France"},
        },
        {
            "id": "doc_003",
            "text": "Machine learning is a subset of AI where models learn patterns from data without explicit programming.",
            "metadata": {"topic": "AI"},
        },
        {
            "id": "doc_004",
            "text": "PostgreSQL is a powerful, open-source relational database system with strong SQL compliance.",
            "metadata": {"topic": "databases"},
        },
        {
            "id": "doc_005",
            "text": "The Amazon rainforest produces 20% of the world's oxygen and houses millions of species.",
            "metadata": {"topic": "geography", "country": "Brazil"},
        },
    ])

    # ── Search ─────────────────────────────────────────────────────────────────
    print("\n── Search: 'tell me about AI and neural networks' ──")
    hits = search(collection, "tell me about AI and neural networks", n_results=2)
    for h in hits:
        print(f"  [{h['distance']}] ({h['id']}) {h['document'][:80]}")

    print("\n── Search with metadata filter (topic=geography) ──")
    hits = search(collection, "famous landmarks", n_results=2, where={"topic": "geography"})
    for h in hits:
        print(f"  [{h['distance']}] ({h['id']}) {h['document'][:80]}")

    # ── Single add ─────────────────────────────────────────────────────────────
    add_document(
        collection,
        doc_id="doc_006",
        text="Redis is an in-memory data structure store used as a cache, database, and message broker.",
        metadata={"topic": "databases"},
    )

    # ── Update ─────────────────────────────────────────────────────────────────
    update_document(
        collection,
        doc_id="doc_006",
        new_text="Redis is an open-source, in-memory key-value store supporting strings, hashes, lists, and sets.",
        metadata={"topic": "databases", "type": "cache"},
    )

    # ── Delete ─────────────────────────────────────────────────────────────────
    delete_document(collection, "doc_006")

    print(f"\nCollection now has {collection.count()} documents.")
