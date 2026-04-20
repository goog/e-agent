"""
Import skills.json into ChromaDB
Each skill is stored with its description + code as the searchable document,
and score / created / uses as metadata.
"""

import json
import os
from pathlib import Path

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
        response = self.client.embeddings.create(model=self.model, input=input)
        return [item.embedding for item in response.data]


# ─── Load JSON ────────────────────────────────────────────────────────────────

def load_skills(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ─── Build document text ──────────────────────────────────────────────────────

def skill_to_document(skill_id: str, skill: dict) -> str:
    """
    Combine desc + code into one searchable text block.
    Embedding this together lets you find skills by natural language
    description OR by code pattern.
    """
    return f"{skill['desc']}\n\n{skill['code'][:300]}"


# ─── Import ───────────────────────────────────────────────────────────────────

def import_skills(
    json_path: str,
    api_key: str,
    persist_path: str = "./chroma_skills_db",
    collection_name: str = "skills",
    skip_existing: bool = True,
):
    skills = load_skills(json_path)
    print(f"Loaded {len(skills)} skills from {json_path}")

    embedding_fn = OpenRouterEmbedding(api_key=api_key)
    client = chromadb.PersistentClient(path=persist_path)
    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    # Find which IDs already exist to avoid duplicate errors
    existing_ids = set()
    if skip_existing and collection.count() > 0:
        existing_ids = set(collection.get(include=[])["ids"])

    ids, documents, metadatas = [], [], []

    for skill_id, skill in skills.items():
        if skip_existing and skill_id in existing_ids:
            print(f"  skip  {skill_id}  (already exists)")
            continue

        ids.append(skill_id)
        documents.append(skill_to_document(skill_id, skill))
        metadatas.append({
            "desc":    skill["desc"],
            "score":   skill["score"],
            "created": skill["created"],
            "uses":    skill["uses"],
        })

    if not ids:
        print("Nothing to import.")
        return collection

    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    print(f"Imported {len(ids)} skills → collection '{collection_name}' now has {collection.count()} docs")
    return collection


# ─── Search helper ────────────────────────────────────────────────────────────

def search_skills(collection, query: str, n_results: int = 3, max_distance: float = 0.39):
    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, collection.count()),
        include=["documents", "distances", "metadatas"],
    )
    hits = []
    for i in range(len(results["ids"][0])):
        dist = results["distances"][0][i]
        #print(f"dist {dist}")
        if dist <= max_distance:
            hits.append({
                "id":       results["ids"][0][i],
                "desc":     results["metadatas"][0][i]["desc"],
                "distance": round(dist, 4),
                "score":    results["metadatas"][0][i]["score"],
                "created":  results["metadatas"][0][i]["created"],
            })
    return hits


def get_skill_collection(persist_path: str = "./chroma_skills_db"):
    collection_name = "skills"
    my_key = os.environ.get("OPENROUTER_API_KEY", "your-openrouter-api-key")
    embedding_fn = OpenRouterEmbedding(api_key=my_key)
    client = chromadb.PersistentClient(path=persist_path)
    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )
    return collection

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    API_KEY   = os.environ.get("OPENROUTER_API_KEY", "your-openrouter-api-key")
    #JSON_PATH = os.environ.get("SKILLS_JSON", "skills.json")
    JSON_PATH = "./agent_workspace/.memory/" + "skills.json"
    col = get_skill_collection()
    result = search_skills(col, "generate a markdown calendar in python")
    print(result)
