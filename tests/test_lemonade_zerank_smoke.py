from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lemonade_zerank_smoke import (
    _stop_lemond,
    _start_lemond,
    _error_payload_message,
    _scores_by_document,
    validate_arithmetic_fixture,
    validate_capital_france_fixture,
    validate_model_metadata,
)


def test_validate_model_metadata_requires_zeroentropy_adapter_options():
    validate_model_metadata(
        {
            "id": "zerank-2-GGUF",
            "downloaded": False,
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


def test_error_payload_message_accepts_non_dict_errors():
    assert _error_payload_message({"message": "bad request"}) == "bad request"
    assert _error_payload_message("bad request") == "bad request"
    assert _error_payload_message(["bad", "request"]) == "['bad', 'request']"


def test_scores_by_document_rejects_duplicate_and_out_of_range_indices():
    documents = ["a", "b"]

    assert _scores_by_document(
        {
            "results": [
                {"index": 1, "relevance_score": 0.25},
                {"index": 0, "relevance_score": 0.75},
            ]
        },
        documents,
    ) == {"a": 0.75, "b": 0.25}

    with pytest.raises(AssertionError, match="duplicate result index"):
        _scores_by_document(
            {
                "results": [
                    {"index": 0, "relevance_score": 0.75},
                    {"index": 0, "relevance_score": 0.25},
                ]
            },
            documents,
        )

    with pytest.raises(AssertionError, match="result index out of bounds"):
        _scores_by_document(
            {
                "results": [
                    {"index": 0, "relevance_score": 0.75},
                    {"index": 2, "relevance_score": 0.25},
                ]
            },
            documents,
        )


def test_start_lemond_cleans_owned_resources_when_launch_fails(tmp_path, monkeypatch):
    server_log = tmp_path / "server.log"
    cache_dir = tmp_path / "owned-cache"

    def fake_mkdtemp(*args, **kwargs):
        cache_dir.mkdir()
        return str(cache_dir)

    def fail_popen(*args, **kwargs):
        raise OSError("cannot launch")

    monkeypatch.setattr("lemonade_zerank_smoke.tempfile.mkdtemp", fake_mkdtemp)
    monkeypatch.setattr("lemonade_zerank_smoke.subprocess.Popen", fail_popen)
    args = argparse.Namespace(
        port=12345,
        host="127.0.0.1",
        cache_dir=None,
        server_log=server_log,
        llama_server="/missing/llama-server",
        lemond="/missing/lemond",
    )

    with pytest.raises(OSError, match="cannot launch"):
        _start_lemond(args)

    assert server_log.exists()
    assert server_log.read_text() == ""
    assert not cache_dir.exists()


def test_stop_lemond_kills_process_after_terminate_timeout(monkeypatch):
    calls = []

    class FakeProcess:
        def __init__(self):
            self.wait_calls = 0

        def wait(self, timeout=None):
            self.wait_calls += 1
            calls.append(("wait", timeout))
            if self.wait_calls < 3:
                raise subprocess.TimeoutExpired("lemond", timeout)
            return 0

        def terminate(self):
            calls.append(("terminate", None))

        def kill(self):
            calls.append(("kill", None))

    monkeypatch.setattr("lemonade_zerank_smoke._shutdown", lambda *args, **kwargs: None)

    _stop_lemond("http://127.0.0.1:12345", FakeProcess())

    assert calls == [
        ("wait", 15.0),
        ("terminate", None),
        ("wait", 15.0),
        ("kill", None),
        ("wait", 15.0),
    ]
