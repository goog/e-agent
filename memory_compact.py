"""
AI Agent Memory Compaction
--------------------------
Compresses a long conversation history into a compact summary that preserves:
  - The original goal / task
  - Key facts, decisions, and conclusions
  - Recent messages (kept verbatim for continuity)

Uses the Anthropic API for the summarisation step.
"""

from __future__ import annotations

import os
import textwrap
from dataclasses import dataclass, field
from typing import Literal

from openai import OpenAI

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

Role = Literal["user", "assistant", "system"]


@dataclass
class Message:
    role: Role
    content: str


@dataclass
class AgentMemory:
    """Holds the full conversation and the compacted state."""

    goal: str                          # The agent's stated objective
    messages: list[Message] = field(default_factory=list)
    compacted_summary: str = ""        # Running summary of older turns
    total_compactions: int = 0

    # Tuning knobs
    max_messages_before_compact: int = 20   # Trigger compaction above this
    recent_messages_to_keep: int = 6        # Always keep the N newest messages

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def add(self, role: Role, content: str) -> None:
        self.messages.append(Message(role=role, content=content))
        if len(self.messages) >= self.max_messages_before_compact:
            self.compact()

    def compact(self) -> str:
        """
        Summarise the oldest messages and discard them, keeping only
        `recent_messages_to_keep` verbatim turns plus the new summary.
        """
        if len(self.messages) <= self.recent_messages_to_keep:
            return self.compacted_summary   # nothing to do

        to_summarise = self.messages[: -self.recent_messages_to_keep]
        recent        = self.messages[-self.recent_messages_to_keep :]

        self.compacted_summary = _summarise(
            goal             = self.goal,
            prior_summary    = self.compacted_summary,
            messages         = to_summarise,
        )
        self.messages           = recent
        self.total_compactions += 1
        return self.compacted_summary

    def build_context(self) -> list[dict]:
        """
        Return the message list to pass to the Anthropic API.
        Injects the compacted summary as a system-style context block when present.
        """
        context: list[dict] = []

        # Prepend summary as the first assistant turn (a common pattern)
        if self.compacted_summary:
            context.append({
                "role": "user",
                "content": (
                    "[Memory summary from earlier in our conversation]\n\n"
                    + self.compacted_summary
                ),
            })
            context.append({
                "role": "assistant",
                "content": "Understood. I have the context from earlier. How can I continue helping?",
            })

        for m in self.messages:
            context.append({"role": m.role, "content": m.content})

        return context

    def stats(self) -> dict:
        return {
            "live_messages":    len(self.messages),
            "total_compactions": self.total_compactions,
            "summary_chars":    len(self.compacted_summary),
        }


# ---------------------------------------------------------------------------
# Summarisation helper (calls the Anthropic API)
# ---------------------------------------------------------------------------

def _summarise(
    goal: str,
    prior_summary: str,
    messages: list[Message],
) -> str:
    """Ask Claude to compress `messages` into a concise summary."""

    #client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from env
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key="<OPENROUTER_API_KEY>",
    )


    history_text = "\n".join(
        f"[{m.role.upper()}]: {m.content}" for m in messages
    )

    prior_block = (
        f"PRIOR SUMMARY:\n{prior_summary}\n\n" if prior_summary else ""
    )

    prompt = textwrap.dedent(f"""
        You are a memory compactor for an AI agent.

        AGENT GOAL: {goal}

        {prior_block}CONVERSATION TO SUMMARISE:
        {history_text}

        Write a concise summary (≤ 300 words) that:
        1. Restates the agent goal in one sentence.
        2. Lists key facts, decisions, tool results, or conclusions reached.
        3. Notes any unresolved questions or next steps.
        4. Preserves numbers, names, and specifics that may be needed later.

        Do NOT include pleasantries. Be terse and factual.
    """).strip()

    response = client.chat.completions.create(
        model="anthropic/claude-sonnet-4.6",
        messages=[
            {
            "role": "user",
            "content": "How many r's are in the word 'strawberry'?"
            }
        ],
        extra_body={"reasoning": {"enabled": True}}
    )
    resp = response.choices[0].message
    print(f"resp {resp}")
    return resp.get('content', '')


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def _demo() -> None:
    """
    Simulate a 25-turn research conversation so compaction fires automatically,
    then print the resulting summary and context structure.
    """
    print("=" * 60)
    print("AI Agent Memory Compaction – Demo")
    print("=" * 60)

    memory = AgentMemory(
        goal                       = "Research the top 3 open-source vector databases and recommend the best one for a Python RAG pipeline.",
        max_messages_before_compact = 10,   # low threshold for the demo
        recent_messages_to_keep    = 4,
    )

    # Simulate a multi-turn conversation
    fake_turns = [
        ("user",      "Let's start. What vector databases should we consider?"),
        ("assistant", "Good choices are Qdrant, Weaviate, Chroma, Milvus, and pgvector."),
        ("user",      "Focus on Qdrant, Chroma, and Weaviate. What are the key differences?"),
        ("assistant", "Qdrant is written in Rust – fast and memory-efficient. Chroma is pure-Python and easiest to embed locally. Weaviate is the most feature-rich (GraphQL, multi-modal) but heavier."),
        ("user",      "What about Python SDK quality?"),
        ("assistant", "All three have official Python SDKs. Chroma's is the simplest. Qdrant's SDK is typed and async-ready. Weaviate's SDK is powerful but verbose."),
        ("user",      "Persistence options?"),
        ("assistant", "Chroma: in-memory or SQLite/DuckDB on disk. Qdrant: in-memory or persistent with snapshots. Weaviate: persistent via embedded RocksDB."),
        ("user",      "Which handles metadata filtering best?"),
        ("assistant", "Qdrant has the most expressive payload filter DSL. Weaviate's GraphQL WHERE clause is powerful. Chroma's filter support is adequate but limited."),
        ("user",      "Cost / hosting?"),
        ("assistant", "All are open-source (Apache 2 / BSD). Qdrant and Weaviate offer managed cloud. Chroma is typically self-hosted."),
        ("user",      "Given a Python RAG pipeline needing fast similarity search + metadata filters, which do you recommend?"),
        ("assistant", "I recommend Qdrant: best performance, rich filtering, strong Python SDK, and straightforward persistence."),
        # More turns to push past the compaction threshold a second time
        ("user",      "How do I install Qdrant locally?"),
        ("assistant", "`pip install qdrant-client` then run the server via Docker: `docker run -p 6333:6333 qdrant/qdrant`."),
        ("user",      "Show me how to create a collection."),
        ("assistant", "```python\nfrom qdrant_client import QdrantClient, models\nclient = QdrantClient('localhost', port=6333)\nclient.create_collection('my_docs', vectors_config=models.VectorParams(size=1536, distance=models.Distance.COSINE))\n```"),
        ("user",      "How do I upsert vectors?"),
        ("assistant", "Use `client.upsert(collection_name='my_docs', points=[models.PointStruct(id=1, vector=[...], payload={'text': 'hello'})])`."),
        ("user",      "And search?"),
        ("assistant", "`client.search(collection_name='my_docs', query_vector=[...], limit=5)` returns the top-5 hits with scores."),
    ]

    for role, content in fake_turns:
        print(f"\n[{role.upper()}] {content[:80]}{'…' if len(content) > 80 else ''}")
        memory.add(role, content)  # type: ignore[arg-type]
        if memory.total_compactions > 0:
            print(f"  ↳ Compaction #{memory.total_compactions} triggered (stats: {memory.stats()})")

    print("\n" + "=" * 60)
    print("FINAL COMPACTED SUMMARY")
    print("=" * 60)
    print(memory.compacted_summary or "(no compaction triggered yet)")

    print("\n" + "=" * 60)
    print("CONTEXT SENT TO NEXT API CALL  (roles only)")
    print("=" * 60)
    for i, msg in enumerate(memory.build_context(), 1):
        preview = msg["content"][:70].replace("\n", " ")
        print(f"  {i:>2}. [{msg['role']}] {preview}…")

    print("\nStats:", memory.stats())


if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: Set the ANTHROPIC_API_KEY environment variable first.")
    else:
        _demo()
