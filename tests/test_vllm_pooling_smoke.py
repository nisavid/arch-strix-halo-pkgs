from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from vllm_pooling_smoke import (
    embedding_vector,
    score_value,
    validate_embedding_fixture,
    validate_rerank_fixture,
)


def test_vllm_pooling_smoke_exposes_help_without_importing_vllm():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools/vllm_pooling_smoke.py"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Run a vLLM pooling smoke" in result.stdout
    assert "--mode" in result.stdout
    assert "--attention-backend" in result.stdout


def test_embedding_vector_accepts_vllm_embedding_output_shape():
    output = SimpleNamespace(outputs=SimpleNamespace(embedding=[0.25, -0.5, 0.75]))

    assert embedding_vector(output) == [0.25, -0.5, 0.75]


def test_score_value_accepts_vllm_scoring_output_shape():
    output = SimpleNamespace(outputs=SimpleNamespace(score=0.875))

    assert score_value(output) == 0.875


def test_validate_embedding_fixture_checks_shape_finite_values_and_ranking(capsys):
    vectors = [
        [1.0, 0.0, 0.0],
        [0.9, 0.1, 0.0],
        [0.0, 1.0, 0.0],
    ]

    validate_embedding_fixture(vectors)

    output = capsys.readouterr().out
    assert "embedding_count 3" in output
    assert "embedding_dim 3" in output
    assert "embeddings_finite_ok" in output
    assert "embedding_ranking_ok" in output


def test_validate_rerank_fixture_checks_finite_scores_and_ordering(capsys):
    validate_rerank_fixture([0.95, 0.15, -0.35])

    output = capsys.readouterr().out
    assert "score_count 3" in output
    assert "scores_finite_ok" in output
    assert "rerank_order 0,1,2" in output
    assert "rerank_order_ok" in output
