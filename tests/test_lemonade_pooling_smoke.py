from __future__ import annotations

from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lemonade_pooling_smoke import (
    embedding_vectors,
    rerank_scores,
    validate_embedding_fixture,
    validate_rerank_fixture,
)


def test_extracts_openai_embedding_vectors():
    payload = {
        "data": [
            {"embedding": [1.0, 0.0]},
            {"embedding": [0.5, 0.5]},
        ]
    }

    assert embedding_vectors(payload) == [[1.0, 0.0], [0.5, 0.5]]


def test_extracts_lemonade_rerank_scores_in_input_order():
    payload = {
        "results": [
            {"index": 0, "relevance_score": 9.0},
            {"index": 1, "relevance_score": 1.0},
        ]
    }

    assert rerank_scores(payload) == [9.0, 1.0]


def test_embedding_fixture_checks_shape_and_finite_values():
    validate_embedding_fixture([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])

    with pytest.raises(AssertionError, match="embedding dimensions differ"):
        validate_embedding_fixture([[1.0], [2.0, 3.0], [4.0]])


def test_rerank_fixture_requires_sorted_scores_after_client_sort():
    validate_rerank_fixture([7.0, 0.0, -4.0])

    with pytest.raises(AssertionError, match="rerank fixture expected"):
        validate_rerank_fixture([0.0, 7.0, -4.0])
