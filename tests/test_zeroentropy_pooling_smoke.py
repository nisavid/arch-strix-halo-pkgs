from __future__ import annotations

from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from zeroentropy_pooling_smoke import (
    format_zembed_inputs,
    validate_embedding_fixture,
    validate_rerank_fixture,
)


def test_zembed_inputs_use_query_and_document_prompts():
    query, *documents = format_zembed_inputs("capital of France", ["Paris", "Berlin"])

    assert "<|im_start|>system\nquery<|im_end|>" in query
    assert query.endswith("<|im_end|>\n")
    assert all("<|im_start|>system\ndocument<|im_end|>" in document for document in documents)
    assert all(document.endswith("<|im_end|>\n") for document in documents)


def test_embedding_fixture_requires_related_document_above_unrelated():
    validate_embedding_fixture(
        [
            [1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0],
            [0.0, 1.0, 0.0],
        ]
    )

    with pytest.raises(AssertionError, match="embedding ranking expected"):
        validate_embedding_fixture(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.9, 0.1, 0.0],
            ]
        )


def test_rerank_fixture_requires_paris_berlin_unrelated_order():
    validate_rerank_fixture([0.9, 0.4, 0.1])

    with pytest.raises(AssertionError, match="rerank fixture expected"):
        validate_rerank_fixture([0.1, 0.9, 0.4])
