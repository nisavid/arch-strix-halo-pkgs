from __future__ import annotations

from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from inference.scenario_loader import load_scenarios
from zeroentropy_pooling_smoke import (
    format_zembed_inputs,
    validate_embedding_fixture,
    validate_zerank_rerank_fixture,
)


def _scores_for_order(order: tuple[int, ...]) -> list[float]:
    scores = [0.0] * len(order)
    for rank, index in enumerate(order):
        scores[index] = 0.75 - 0.2 * rank
    return scores


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


# vLLM 0.30 and Lemonade rank "Two plus two equals four." above "4"; the
# 2026-04-21 Transformers pass ranked "4" first.
@pytest.mark.parametrize("order", [(1, 0, 2), (0, 1, 2)])
def test_zerank_fixture_accepts_either_correct_answer_first(order, capsys):
    scores = _scores_for_order(order)

    validate_zerank_rerank_fixture(scores)

    output = capsys.readouterr().out
    assert f"rerank_scores {','.join(str(score) for score in scores)}" in output
    assert f"rerank_order {','.join(str(index) for index in order)}" in output
    assert "score_count 3" in output
    assert "scores_finite_ok" in output
    assert "rerank_distractor_last_ok" in output
    assert "rerank_order_ok" in output


@pytest.mark.parametrize("order", [(0, 2, 1), (1, 2, 0), (2, 0, 1), (2, 1, 0)])
def test_zerank_fixture_rejects_distractor_above_a_correct_answer(order, capsys):
    with pytest.raises(AssertionError, match="both correct answers above the distractor"):
        validate_zerank_rerank_fixture(_scores_for_order(order))

    output = capsys.readouterr().out
    assert "rerank_scores " in output
    assert f"rerank_order {','.join(str(index) for index in order)}" in output
    assert "rerank_order_ok" not in output


def test_zerank_fixture_rejects_tied_distractor():
    with pytest.raises(AssertionError, match="both correct answers above the distractor"):
        validate_zerank_rerank_fixture([0.75, 0.5, 0.5])


def test_zerank_fixture_rejects_non_finite_scores():
    with pytest.raises(AssertionError, match="score_1_not_finite"):
        validate_zerank_rerank_fixture([0.75, float("nan"), 0.25])


def test_transformers_zerank_scenario_asserts_lines_the_fixture_prints(capsys):
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    (scenario,) = [
        scenario
        for scenario in scenarios
        if scenario.id == "transformers.zeroentropy.zerank-2.rerank"
    ]
    expected = [
        assertion["value"]
        for assertion in scenario.definition["then"]["assert"]
        if assertion["kind"] == "stdout.contains"
    ]

    print("mode rerank")
    validate_zerank_rerank_fixture(_scores_for_order((1, 0, 2)))
    print("rerank_ok")

    output = capsys.readouterr().out
    assert "rerank_distractor_last_ok" in expected
    assert [value for value in expected if value not in output] == []
