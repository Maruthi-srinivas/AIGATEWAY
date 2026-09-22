from aigateway.gateway.classify import is_chitchat
from aigateway.rag.chunking import CHUNK_OVERLAP, CHUNK_SIZE, MAX_CHUNKS, MAX_TEXT_BYTES, chunk_text
from aigateway.rag.embeddings import fixture_embedding
from aigateway.rag.models import EMBED_DIM


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def test_chitchat_matches_cleaned_phrases() -> None:
    assert is_chitchat("Hello!")
    assert is_chitchat("thank you")
    assert not is_chitchat("how many paid time off days")
    assert not is_chitchat("hello again")


def test_chunk_text_uses_character_windows() -> None:
    text = "a" * (CHUNK_SIZE + 10)
    parts = chunk_text(text)
    assert parts[0] == text[:CHUNK_SIZE]
    assert len(parts[1]) == 10 + CHUNK_OVERLAP
    assert len(chunk_text("a" * (CHUNK_SIZE * MAX_CHUNKS + 50))) == MAX_CHUNKS
    assert MAX_TEXT_BYTES == 262144


def test_fixture_embedding_is_unit_256d_and_retrieves_overlap() -> None:
    vector = fixture_embedding("Acme HR paid time off is twenty days per year.")
    assert len(vector) == EMBED_DIM
    assert abs(sum(value * value for value in vector) - 1.0) < 1e-6
    query = fixture_embedding("How many paid time off days per year does Acme HR give?")
    other = fixture_embedding("The pager escalation goes to the incident commander.")
    assert _cosine(query, vector) > 0.3
    assert _cosine(query, vector) > _cosine(query, other)
