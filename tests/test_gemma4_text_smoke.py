from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from gemma4_text_smoke import (
    build_llm_kwargs,
    correctness_checks,
    effective_gpu_memory_utilization,
    effective_max_model_len,
    effective_max_num_batched_tokens,
    resolved_model_arg,
)


def test_gemma4_text_smoke_exposes_help_without_importing_vllm():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools/gemma4_text_smoke.py"), "--help"],
        check=False,
        timeout=30,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Run a text-only offline Gemma 4 instruction-tuned smoke" in result.stdout
    assert "--execution-mode" in result.stdout


def test_resolved_model_arg_preserves_hf_model_ids(tmp_path: Path):
    model_dir = tmp_path / "google" / "gemma-4-26B-A4B-it"
    model_dir.mkdir(parents=True)

    assert resolved_model_arg("google/gemma-4-26B-A4B-it") == "google/gemma-4-26B-A4B-it"
    assert resolved_model_arg(str(model_dir)) == str(model_dir.resolve())


def test_gemma4_26b_uses_batched_token_default():
    args = SimpleNamespace(max_num_batched_tokens=None)

    assert effective_max_num_batched_tokens(args, "google/gemma-4-26B-A4B-it") == 32
    assert effective_max_num_batched_tokens(args, "google/gemma-4-E2B-it") is None


def test_gemma4_text_smoke_uses_tighter_e2b_memory_default():
    default_args = SimpleNamespace(gpu_memory_utilization=None)
    override_args = SimpleNamespace(gpu_memory_utilization=0.55)

    assert effective_gpu_memory_utilization(default_args, "google/gemma-4-E2B-it") == 0.35
    assert effective_gpu_memory_utilization(default_args, "google/gemma-4-26B-A4B-it") == 0.75
    assert effective_gpu_memory_utilization(override_args, "google/gemma-4-E2B-it") == 0.55


def test_build_llm_kwargs_uses_resolved_model_id():
    args = SimpleNamespace(
        execution_mode="eager",
        gpu_memory_utilization=0.45,
        max_model_len=128,
    )

    kwargs = build_llm_kwargs(
        "google/gemma-4-26B-A4B-it",
        args,
        max_num_batched_tokens=32,
    )

    assert kwargs["model"] == "google/gemma-4-26B-A4B-it"
    assert kwargs["gpu_memory_utilization"] == 0.45
    assert kwargs["max_num_batched_tokens"] == 32
    assert kwargs["enforce_eager"] is True


def test_gemma4_text_smoke_help_lists_correctness_checks():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools/gemma4_text_smoke.py"), "--help"],
        check=False,
        timeout=30,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--known-answer" in result.stdout
    assert "--long-decode" in result.stdout


def test_gemma4_text_smoke_long_decode_raises_default_max_model_len():
    basic = SimpleNamespace(max_model_len=None, long_decode=False, long_decode_count=150)
    long_decode = SimpleNamespace(max_model_len=None, long_decode=True, long_decode_count=150)
    wide = SimpleNamespace(max_model_len=None, long_decode=True, long_decode_count=250)
    explicit = SimpleNamespace(max_model_len=2048, long_decode=True, long_decode_count=250)

    assert effective_max_model_len(basic) == 128
    assert effective_max_model_len(long_decode) == 1024
    assert effective_max_model_len(wide) == 1536
    assert effective_max_model_len(explicit) == 2048


def test_gemma4_text_smoke_correctness_checks_are_opt_in_and_greedy_sized():
    none = SimpleNamespace(known_answer=False, long_decode=False, long_decode_count=150)
    both = SimpleNamespace(known_answer=True, long_decode=True, long_decode_count=120)

    assert correctness_checks(none) == []
    checks = correctness_checks(both)
    assert [check.name for check in checks] == ["known_answer", "long_decode"]
    assert "first ten prime numbers" in checks[0].prompt
    assert checks[0].max_tokens == 64
    assert "count from 1 to 120" in checks[1].prompt
    assert checks[1].max_tokens == 800
    checks[0].validate("2, 3, 5, 7, 11, 13, 17, 19, 23, 29")
    checks[1].validate(
        ", ".join(str(value) for value in range(1, 121)) + "\nCode word: PELICAN"
    )


def test_gemma4_text_smoke_long_decode_max_tokens_follow_the_count():
    wide = SimpleNamespace(known_answer=False, long_decode=True, long_decode_count=250)

    (check,) = correctness_checks(wide)
    assert "count from 1 to 250" in check.prompt
    assert check.max_tokens == 1250
