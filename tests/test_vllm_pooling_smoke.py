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
    RERANK_DOCUMENTS,
    RERANK_QUERY,
    embedding_vector,
    _llm_kwargs,
    score_value,
    run_rerank,
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


def test_llm_kwargs_for_rerank_selects_classification_conversion():
    args = SimpleNamespace(
        mode="rerank",
        attention_backend="FLEX_ATTENTION",
        gpu_memory_utilization=0.5,
        max_model_len=512,
        max_num_batched_tokens=None,
    )

    kwargs = _llm_kwargs(args, "jinaai/jina-reranker-v3")

    assert kwargs["convert"] == "classify"
    assert kwargs["pooler_config"] == {"task": "classify"}


def test_run_rerank_scores_pairs_with_classification_pooling(monkeypatch):
    pooling_params = object()
    monkeypatch.setattr(
        "vllm_pooling_smoke.classification_pooling_params",
        lambda: pooling_params,
    )
    output = SimpleNamespace(outputs=SimpleNamespace(score=0.875))

    class FakeLLM:
        def __init__(self) -> None:
            self.score_calls = []

        def score(self, query, documents, **kwargs):
            self.score_calls.append((query, documents, kwargs))
            return [output, output, output]

    llm = FakeLLM()

    run_rerank(llm)

    assert llm.score_calls == [
        (
            RERANK_QUERY,
            RERANK_DOCUMENTS,
            {"use_tqdm": False, "pooling_params": pooling_params},
        )
    ]


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
