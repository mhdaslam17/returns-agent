import pytest

from returns_agent.config import POLICY_PATH
from returns_agent.rag import split_policy


def test_policy_is_split_by_clause():
    chunks = split_policy(POLICY_PATH.read_text(encoding="utf-8"))
    clauses = [c.clause for c in chunks]
    assert len(clauses) == len(set(clauses))
    for expected in ["1.1", "2.1", "2.7", "3.1", "3.4", "5.3", "6.2", "7.1", "8.3", "10.1"]:
        assert expected in clauses
    pillow = next(c for c in chunks if c.clause == "2.7")
    assert pillow.section == "The 100-night trial"
    assert "hygiene" in pillow.text


# The search tests download a small embedding model the first time (~120 MB).
@pytest.fixture(scope="module")
def index():
    pytest.importorskip("sentence_transformers")
    from returns_agent.rag import get_policy_index

    return get_policy_index()


@pytest.mark.parametrize("query, clause", [
    ("Can I return a pillow I already opened?", "2.7"),
    ("Please refund to my new card, the old one is closed", "3.1"),
    ("My lawyer will take you to court", "7.1"),
    ("I was charged twice for the same order", "6.1"),
    ("أريد إرجاع المرتبة، نمت عليها أسبوعين فقط", "2.3"),     # Arabic: return after only two weeks
    ("المرتبة فيها هبوط في النص", "5.2"),                      # Arabic: sag in the middle
])
def test_search_finds_the_right_clause(index, query, clause):
    top = [hit["clause"] for hit in index.search(query, k=4)]
    assert clause in top, f"{query!r}: expected {clause} in {top}"
