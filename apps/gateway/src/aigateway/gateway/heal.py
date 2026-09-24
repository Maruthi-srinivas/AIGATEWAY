from __future__ import annotations

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "do",
        "does",
        "for",
        "how",
        "in",
        "is",
        "long",
        "many",
        "of",
        "on",
        "or",
        "the",
        "to",
        "was",
        "what",
        "who",
    }
)


def rewrite_query(query: str) -> str:
    words = [word for word in query.lower().split() if word not in STOPWORDS]
    return " ".join(words)
