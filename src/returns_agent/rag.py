"""Policy search (RAG) over data/policy.md.

Design:
- Chunk by numbered clause (2.1, 2.2, ...). One clause is one rule, so the agent
  can cite it ("policy 2.3"). Each chunk also gets its section title for context.
- Embeddings: a local multilingual model (Arabic + English), free, no API key.
  e5 models expect "query: " and "passage: " prefixes.
- Index: FAISS inner product on normalized vectors = cosine similarity.
  The policy is small, so the index is built in memory at start.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import faiss
import numpy as np

from returns_agent.config import EMBEDDING_MODEL, POLICY_PATH

SECTION_RE = re.compile(r"^## (\d+)\. (.+)$")
CLAUSE_RE = re.compile(r"^(\d+\.\d+) ")


@dataclass(frozen=True)
class PolicyChunk:
    clause: str        # "2.3"
    section: str       # "The 100-night trial"
    text: str


def split_policy(markdown: str) -> list[PolicyChunk]:
    chunks: list[PolicyChunk] = []
    section, clause, lines = "", None, []

    def flush():
        if clause and lines:
            chunks.append(PolicyChunk(clause, section, " ".join(lines).strip()))

    for raw in markdown.splitlines():
        line = raw.strip()
        if m := SECTION_RE.match(line):
            flush()
            section, clause, lines = m.group(2), None, []
        elif m := CLAUSE_RE.match(line):
            flush()
            clause, lines = m.group(1), [line[len(m.group(0)):]]
        elif clause and line:
            lines.append(line)
        elif clause and not line:
            flush()
            clause, lines = None, []
    flush()
    return chunks


class PolicyIndex:
    def __init__(self, chunks: list[PolicyChunk], model_name: str = EMBEDDING_MODEL):
        from sentence_transformers import SentenceTransformer  # slow import, so done here

        self.chunks = chunks
        self.model = SentenceTransformer(model_name)
        passages = [f"passage: {c.section}. {c.clause} {c.text}" for c in chunks]
        vectors = self.model.encode(passages, normalize_embeddings=True)
        self.index = faiss.IndexFlatIP(vectors.shape[1])
        self.index.add(np.asarray(vectors, dtype="float32"))

    def search(self, query: str, k: int = 4) -> list[dict]:
        vector = self.model.encode([f"query: {query}"], normalize_embeddings=True)
        scores, ids = self.index.search(np.asarray(vector, dtype="float32"), k)
        return [
            {"clause": self.chunks[i].clause, "section": self.chunks[i].section,
             "text": self.chunks[i].text, "score": round(float(s), 3)}
            for s, i in zip(scores[0], ids[0]) if i != -1
        ]


@lru_cache(maxsize=1)
def get_policy_index(path: Path = POLICY_PATH) -> PolicyIndex:
    return PolicyIndex(split_policy(path.read_text(encoding="utf-8")))


def check_policy(query: str, k: int = 4) -> list[dict]:
    """The check_policy tool: the k policy clauses closest to the query."""
    return get_policy_index().search(query, k)
