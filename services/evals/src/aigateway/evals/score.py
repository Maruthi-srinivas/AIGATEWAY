from __future__ import annotations

I_DONT_KNOW = "I don't know based on the available documents."


def score_answer(
    *,
    answer: str,
    chunks: list[str],
    expected_terms: list[str],
    groundedness: float | None,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Lexical scores. Faithfulness follows groundedness, except the exact I-don't-know sentence."""
    faithfulness = groundedness
    if answer.strip() == I_DONT_KNOW and groundedness is None:
        faithfulness = 1.0
    terms = [term.lower() for term in expected_terms if term.strip()]
    if not terms:
        return faithfulness, None, None, None
    recall = _share(terms, lambda term: any(term in chunk.lower() for chunk in chunks))
    if chunks:
        precision = _share(
            chunks,
            lambda chunk: any(term in chunk.lower() for term in terms),
        )
    else:
        precision = 0.0
    correctness = _share(terms, lambda term: term in answer.lower())
    return faithfulness, recall, precision, correctness


def _share(items: list[str], predicate) -> float:
    if not items:
        return 0.0
    return sum(1 for item in items if predicate(item)) / len(items)
