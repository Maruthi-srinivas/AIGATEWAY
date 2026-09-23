from aigateway.contracts import RetrievedChunk
from aigateway.gateway.grounding import I_DONT_KNOW, split_sentences, verify_answer


def _chunk(content: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="cccccccccccccccccccccccccccccccccccc",
        document_id="dddddddddddddddddddddddddddddddddddd",
        content=content,
        score=0.9,
    )


def test_decimal_stays_one_sentence() -> None:
    assert split_sentences("The value is 3.14 today.") == ["The value is 3.14 today."]


def test_half_of_the_tokens_is_enough() -> None:
    text, citations, groundedness, dropped, redacted = verify_answer(
        "Alpha beta.",
        [_chunk("alpha belongs in this note")],
    )
    assert text == "Alpha beta."
    assert groundedness == 1.0
    assert dropped == 0
    assert citations
    assert redacted is False


def test_less_than_half_is_dropped() -> None:
    text, citations, groundedness, dropped, redacted = verify_answer(
        "Alpha beta gamma.",
        [_chunk("alpha only")],
    )
    assert text == I_DONT_KNOW
    assert citations == []
    assert groundedness == 0.0
    assert dropped == 1
    assert redacted is False
