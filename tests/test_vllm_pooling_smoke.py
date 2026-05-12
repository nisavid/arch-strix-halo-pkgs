from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import types
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from vllm_pooling_smoke import (
    RERANK_DOCUMENTS,
    RERANK_QUERY,
    ZEROENTROPY_EMBEDDING_DOCUMENTS,
    ZEROENTROPY_EMBEDDING_QUERY,
    ZEROENTROPY_RERANK_DOCUMENTS,
    ZEROENTROPY_RERANK_QUERY,
    embedding_vector,
    _llm_kwargs,
    score_value,
    run_rerank,
    run_zeroentropy_embeddings,
    run_zeroentropy_rerank,
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
    assert "--fixture" in result.stdout


def test_embedding_vector_accepts_vllm_embedding_output_shape():
    output = SimpleNamespace(outputs=SimpleNamespace(embedding=[0.25, -0.5, 0.75]))

    assert embedding_vector(output) == [0.25, -0.5, 0.75]


def test_score_value_accepts_vllm_scoring_output_shape():
    output = SimpleNamespace(outputs=SimpleNamespace(score=0.875))

    assert score_value(output) == 0.875


def test_score_value_accepts_vllm_classification_output_shape():
    output = SimpleNamespace(outputs=SimpleNamespace(probs=[0.875]))

    assert score_value(output) == 0.875


def test_llm_kwargs_for_rerank_selects_classification_conversion():
    args = SimpleNamespace(
        mode="rerank",
        fixture="generic",
        attention_backend="FLEX_ATTENTION",
        gpu_memory_utilization=0.5,
        max_model_len=512,
        max_num_batched_tokens=None,
    )

    kwargs = _llm_kwargs(args, "example/reranker")

    assert kwargs["convert"] == "classify"
    assert kwargs["pooler_config"] == {"task": "classify"}


def test_llm_kwargs_for_zeroentropy_embeddings_selects_embedding_conversion():
    args = SimpleNamespace(
        mode="embeddings",
        fixture="zeroentropy",
        attention_backend="FLEX_ATTENTION",
        gpu_memory_utilization=0.5,
        max_model_len=256,
        max_num_batched_tokens=None,
    )

    kwargs = _llm_kwargs(args, "zeroentropy/zembed-1")

    assert kwargs["convert"] == "embed"


def test_llm_kwargs_for_zeroentropy_rerank_selects_yes_token_classifier():
    args = SimpleNamespace(
        mode="rerank",
        fixture="zeroentropy",
        attention_backend="FLEX_ATTENTION",
        gpu_memory_utilization=0.5,
        max_model_len=512,
        max_num_batched_tokens=None,
    )

    kwargs = _llm_kwargs(args, "zeroentropy/zerank-2")

    assert kwargs["convert"] == "classify"
    assert kwargs["hf_overrides"] == {
        "classifier_from_token": ["Yes"],
        "method": "no_post_processing",
        "num_labels": 1,
    }
    assert kwargs["pooler_config"] == {
        "task": "classify",
        "logit_sigma": 5.0,
    }


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


def test_run_zeroentropy_embeddings_formats_query_and_documents(capsys):
    outputs = [
        SimpleNamespace(outputs=SimpleNamespace(embedding=[1.0, 0.0, 0.0])),
        SimpleNamespace(outputs=SimpleNamespace(embedding=[0.9, 0.1, 0.0])),
        SimpleNamespace(outputs=SimpleNamespace(embedding=[0.0, 1.0, 0.0])),
    ]

    class FakeLLM:
        def __init__(self) -> None:
            self.embed_calls = []

        def embed(self, prompts, **kwargs):
            self.embed_calls.append((prompts, kwargs))
            return outputs

    llm = FakeLLM()

    run_zeroentropy_embeddings(llm)

    assert llm.embed_calls == [
        (
            [
                "<|im_start|>system\n"
                "query<|im_end|>\n"
                "<|im_start|>user\n"
                f"{ZEROENTROPY_EMBEDDING_QUERY}<|im_end|>\n",
                *[
                    "<|im_start|>system\n"
                    "document<|im_end|>\n"
                    "<|im_start|>user\n"
                    f"{document}<|im_end|>\n"
                    for document in ZEROENTROPY_EMBEDDING_DOCUMENTS
                ],
            ],
            {"use_tqdm": False},
        )
    ]
    output = capsys.readouterr().out
    assert "embedding_ranking_ok" in output
    assert "embeddings_ok" in output


def test_run_zeroentropy_rerank_classifies_formatted_prompts(monkeypatch):
    pooling_params = object()
    vllm_module = types.ModuleType("vllm")
    pooling_module = types.ModuleType("vllm.pooling_params")
    pooling_module.PoolingParams = lambda **_: pooling_params
    monkeypatch.setitem(sys.modules, "vllm", vllm_module)
    monkeypatch.setitem(sys.modules, "vllm.pooling_params", pooling_module)

    class FakeTokenizer:
        def apply_chat_template(self, messages, **kwargs):
            return f"{messages[0]['content']} -> {messages[1]['content']}"

    output = SimpleNamespace(outputs=SimpleNamespace(probs=[0.875]))

    class FakeLLM:
        def __init__(self) -> None:
            self.classify_calls = []

        def get_tokenizer(self):
            return FakeTokenizer()

        def classify(self, prompts, **kwargs):
            self.classify_calls.append((prompts, kwargs))
            return [output, output, output]

    llm = FakeLLM()

    run_zeroentropy_rerank(llm)

    assert llm.classify_calls == [
        (
            [
                f"{ZEROENTROPY_RERANK_QUERY} -> {document}"
                for document in ZEROENTROPY_RERANK_DOCUMENTS
            ],
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

    with pytest.raises(AssertionError, match="descending score ordering"):
        validate_rerank_fixture([0.15, 0.95, -0.35])
