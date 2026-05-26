from __future__ import annotations

from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lemonade_zerank_smoke import (
    validate_arithmetic_fixture,
    validate_capital_france_fixture,
    validate_model_metadata,
)


def test_validate_model_metadata_requires_zeroentropy_adapter_options():
    validate_model_metadata(
        {
            "id": "zerank-2-GGUF",
            "downloaded": True,
            "labels": ["reranking"],
            "recipe": "llamacpp",
            "recipe_options": {
                "llamacpp_reranking_adapter": "zeroentropy-logit-score",
                "llamacpp_reranking_true_token_id": 9454,
                "llamacpp_reranking_logit_scale": 5.0,
            },
        }
    )

    with pytest.raises(AssertionError, match="missing adapter"):
        validate_model_metadata(
            {
                "id": "zerank-2-GGUF",
                "downloaded": True,
                "labels": ["reranking"],
                "recipe": "llamacpp",
                "recipe_options": {},
            }
        )


def test_capital_france_fixture_requires_paris_first_and_finite_scores():
    scores_by_document = {
        "Paris is the capital of France.": 0.96,
        "apple": 0.09,
        "dog": 0.08,
        "tomato": 0.07,
    }

    validate_capital_france_fixture(scores_by_document)

    with pytest.raises(AssertionError, match="expected Paris"):
        validate_capital_france_fixture(
            {
                "Paris is the capital of France.": 0.1,
                "apple": 0.9,
                "dog": 0.08,
                "tomato": 0.07,
            }
        )


def test_arithmetic_fixture_requires_canonical_answer_then_literal_four():
    validate_arithmetic_fixture(
        {
            "Two plus two equals four.": 0.93,
            "4": 0.74,
            "The answer is definitely 1 million.": 0.27,
        }
    )

    with pytest.raises(AssertionError, match="expected arithmetic"):
        validate_arithmetic_fixture(
            {
                "Two plus two equals four.": 0.93,
                "4": 0.1,
                "The answer is definitely 1 million.": 0.74,
            }
        )
