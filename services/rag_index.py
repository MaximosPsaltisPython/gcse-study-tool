from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from services.document_loader import LoadedDocument


@dataclass(frozen=True)
class Chunk:
    id: str
    subject: str
    document_type: str
    source: str
    text: str


@dataclass
class SearchResult:
    chunk: Chunk
    score: float


class StudyIndex:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._doc_tokens = [Counter(tokenize(chunk.text)) for chunk in chunks]
        self._idf = self._build_idf()

    @classmethod
    def from_documents(cls, documents: list[LoadedDocument]) -> "StudyIndex":
        chunks: list[Chunk] = []
        for document in documents:
            for index, text in enumerate(chunk_text(document.text), start=1):
                chunks.append(
                    Chunk(
                        id=f"{document.name}-{index}",
                        subject=document.subject,
                        document_type=document.document_type,
                        source=document.name,
                        text=text,
                    )
                )
        return cls(chunks)

    def search(self, query: str, subject: str | None = None, limit: int = 6) -> list[SearchResult]:
        query_tokens = Counter(tokenize(query))
        if not query_tokens:
            return []

        results: list[SearchResult] = []
        for chunk, doc_tokens in zip(self.chunks, self._doc_tokens):
            if subject and chunk.subject != subject:
                continue
            score = cosine_score(query_tokens, doc_tokens, self._idf)
            if score > 0:
                results.append(SearchResult(chunk=chunk, score=score))

        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]

    def _build_idf(self) -> dict[str, float]:
        document_count = max(len(self._doc_tokens), 1)
        document_frequency: Counter[str] = Counter()
        for tokens in self._doc_tokens:
            document_frequency.update(tokens.keys())

        return {
            token: math.log((document_count + 1) / (count + 1)) + 1
            for token, count in document_frequency.items()
        }


def chunk_text(text: str, max_words: int = 430, overlap: int = 70) -> list[str]:
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = max(end - overlap, start + 1)

    return chunks


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-zA-Z0-9]+", text.lower())
        if len(token) > 2
    ]


def cosine_score(
    query_tokens: Counter[str],
    doc_tokens: Counter[str],
    idf: dict[str, float],
) -> float:
    shared_tokens = set(query_tokens) & set(doc_tokens)
    if not shared_tokens:
        return 0.0

    dot = sum(
        (query_tokens[token] * idf.get(token, 1.0))
        * (doc_tokens[token] * idf.get(token, 1.0))
        for token in shared_tokens
    )
    query_norm = math.sqrt(
        sum((count * idf.get(token, 1.0)) ** 2 for token, count in query_tokens.items())
    )
    doc_norm = math.sqrt(
        sum((count * idf.get(token, 1.0)) ** 2 for token, count in doc_tokens.items())
    )
    if query_norm == 0 or doc_norm == 0:
        return 0.0
    return dot / (query_norm * doc_norm)


def format_context(results: list[SearchResult]) -> str:
    if not results:
        return "No indexed material matched the request."

    context_blocks = []
    for index, result in enumerate(results, start=1):
        context_blocks.append(
            f"Source {index}: {result.chunk.source} "
            f"({result.chunk.document_type}, relevance {result.score:.2f})\n"
            f"{result.chunk.text}"
        )
    return "\n\n---\n\n".join(context_blocks)
