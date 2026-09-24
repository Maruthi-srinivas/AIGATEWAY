from aigateway.evals.score import score_answer
from aigateway.gateway.answer_cache import cache_key
from aigateway.gateway.grounding import I_DONT_KNOW


def test_score_full_hit() -> None:
    faithfulness, recall, precision, correctness = score_answer(
        answer="Paid time off is twenty days.",
        chunks=["twenty days of leave"],
        expected_terms=["twenty", "days"],
        groundedness=1.0,
    )
    assert faithfulness == 1.0
    assert recall == 1.0
    assert precision == 1.0
    assert correctness == 1.0


def test_score_miss() -> None:
    faithfulness, recall, precision, correctness = score_answer(
        answer="No match here.",
        chunks=["unrelated text"],
        expected_terms=["twenty"],
        groundedness=0.0,
    )
    assert faithfulness == 0.0
    assert recall == 0.0
    assert precision == 0.0
    assert correctness == 0.0


def test_score_exact_i_dont_know() -> None:
    faithfulness, recall, precision, correctness = score_answer(
        answer=I_DONT_KNOW,
        chunks=[],
        expected_terms=[],
        groundedness=None,
    )
    assert faithfulness == 1.0
    assert recall is None
    assert precision is None
    assert correctness is None


def test_cache_keys_differ_by_tenant_and_role() -> None:
    base = cache_key("tenant-a", "app_user", "policy", "Hello")
    assert base != cache_key("tenant-b", "app_user", "policy", "Hello")
    assert base != cache_key("tenant-a", "security_admin", "policy", "Hello")
    assert base == cache_key("tenant-a", "app_user", "policy", "  hello  ")
