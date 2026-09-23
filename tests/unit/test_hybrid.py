from aigateway.rag.hybrid import (
    RankedHit,
    apply_char_budget,
    fuse_rrf,
    mask_secrets,
)


def test_rrf_puts_bm25_hit_ahead_of_vector_distractor() -> None:
    fused = fuse_rrf(["distractor", "target"], ["target"])
    ids = [chunk_id for chunk_id, *_rest in fused]
    assert ids.index("target") < ids.index("distractor")


def test_mask_secrets_leaves_stored_pattern_redacted() -> None:
    raw = "The key is sk-abcdefghijklmnopqrstuvwxyz for payroll."
    masked = mask_secrets(raw)
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in masked
    assert "[SECRET]" in masked
    assert raw.startswith("The key is sk-")


def test_char_budget_drops_the_tail() -> None:
    hits = [
        RankedHit(chunk_id=str(index), document_id="d", content="x" * 3000) for index in range(3)
    ]
    kept, dropped = apply_char_budget(hits, 8000)
    assert len(kept) == 2
    assert len(dropped) == 1
    assert dropped[0][1] == "char_budget"
