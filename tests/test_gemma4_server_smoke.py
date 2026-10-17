from __future__ import annotations

import base64
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import sys

from PIL import Image
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "tools/gemma4_server_smoke.py"
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from gemma4_server_smoke import multimodal_content, validate_multimodal_response


def test_long_decode_response_accepts_complete_count_and_recall_without_token_floor():
    from gemma4_server_smoke import validate_long_decode_response

    message = {"content": "1, 2, 3\nCode word: PELICAN"}
    response = {"choices": [{"message": message, "finish_reason": "stop"}]}

    assert validate_long_decode_response(response, count=3) == message


def test_long_decode_response_rejects_truncation_even_with_complete_content():
    from gemma4_server_smoke import validate_long_decode_response

    response = {
        "choices": [{
            "message": {"content": "1, 2, 3\nCode word: PELICAN"},
            "finish_reason": "length",
        }],
    }

    with pytest.raises(RuntimeError, match="truncated"):
        validate_long_decode_response(response, count=3)


def test_long_decode_response_rejects_output_below_requested_token_floor():
    from gemma4_server_smoke import validate_long_decode_response

    response = {
        "choices": [{
            "message": {"content": "1, 2, 3\nCode word: PELICAN"},
            "finish_reason": "stop",
        }],
        "usage": {"completion_tokens": 1024},
    }

    with pytest.raises(RuntimeError, match="at least 1025"):
        validate_long_decode_response(response, count=3, min_completion_tokens=1025)


@pytest.mark.parametrize("usage", [
    None, {}, [], "1025", {"completion_tokens": None},
    {"completion_tokens": True}, {"completion_tokens": "1025"},
    {"completion_tokens": 1025.0}, {"completion_tokens": 1025.5},
    {"completion_tokens": float("nan")}, {"completion_tokens": float("inf")},
    {"completion_tokens": -1},
])
def test_long_decode_response_rejects_missing_or_malformed_usage(usage):
    from gemma4_server_smoke import validate_long_decode_response

    response = {
        "choices": [{
            "message": {"content": "1, 2, 3\nCode word: PELICAN"},
            "finish_reason": "stop",
        }],
        "usage": usage,
    }

    with pytest.raises(RuntimeError, match="completion_tokens.*integer"):
        validate_long_decode_response(response, count=3, min_completion_tokens=1025)


@pytest.mark.parametrize("finish_reason", [None, "", "tool_calls", "content_filter", "unknown"])
def test_long_decode_response_requires_stop_for_measured_token_gate(finish_reason):
    from gemma4_server_smoke import validate_long_decode_response

    response = {
        "choices": [{
            "message": {"content": "1, 2, 3\nCode word: PELICAN"},
            "finish_reason": finish_reason,
        }],
        "usage": {"completion_tokens": 1025},
    }

    with pytest.raises(RuntimeError, match="finish_reason.*stop"):
        validate_long_decode_response(response, count=3, min_completion_tokens=1025)


@pytest.mark.parametrize("response", [
    None, [], {}, {"choices": None}, {"choices": []}, {"choices": "bad"},
    {"choices": [None]}, {"choices": [{"message": None}]},
    {"choices": [{"message": {"content": None}}]},
    {"choices": [{"message": {"content": 7}}]},
    {"choices": [{"message": {"content": ["1", "2", "3"]}}]},
])
def test_long_decode_response_reports_malformed_choice_message_or_content(response):
    from gemma4_server_smoke import validate_long_decode_response

    with pytest.raises(RuntimeError, match="long-decode response"):
        validate_long_decode_response(response, count=3)


@pytest.mark.parametrize("content", [
    "1, 3\nCode word: PELICAN", "1, 2, 2, 3\nCode word: PELICAN",
    "1, 3, 2\nCode word: PELICAN", "1, 2, 3\nCode word: HERON",
    "PELICAN\n1, 2, 3", "", "1, 2, 3\nCode word: PELICAN🦜",
])
def test_long_decode_response_keeps_counting_and_recall_checks_with_token_floor(content):
    from gemma4_server_smoke import validate_long_decode_response

    response = {
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"completion_tokens": 1025},
    }

    with pytest.raises(RuntimeError):
        validate_long_decode_response(response, count=3, min_completion_tokens=1025)


@pytest.mark.parametrize("tokens", [1025, 1146])
def test_long_decode_response_accepts_measured_output_at_or_above_token_floor(tokens):
    from gemma4_server_smoke import validate_long_decode_response

    # Constructed protocol data exercises the gate, not observed model behavior.
    content = ", ".join(str(number) for number in range(1, 251)) + "\nCode word: PELICAN"
    message = {"content": content}
    response = {
        "choices": [{"message": message, "finish_reason": "stop"}],
        "usage": {"completion_tokens": tokens},
    }

    assert validate_long_decode_response(
        response, count=250, min_completion_tokens=1025,
    ) == message


@pytest.mark.parametrize("finish_reason", [None, "stop"])
def test_long_decode_response_without_token_floor_does_not_require_usage(finish_reason):
    from gemma4_server_smoke import validate_long_decode_response

    message = {"content": "1, 2, 3\nCode word: PELICAN"}
    response = {"choices": [{"message": message, "finish_reason": finish_reason}]}

    assert validate_long_decode_response(response, count=3) == message


@pytest.mark.parametrize("minimum", [0, -1, True, "1025", 1025.0])
def test_long_decode_response_rejects_invalid_minimum(minimum):
    from gemma4_server_smoke import validate_long_decode_response

    response = {
        "choices": [{
            "message": {"content": "1, 2, 3\nCode word: PELICAN"},
            "finish_reason": "stop",
        }],
        "usage": {"completion_tokens": 1025},
    }

    with pytest.raises(RuntimeError, match="min_completion_tokens.*positive integer"):
        validate_long_decode_response(response, count=3, min_completion_tokens=minimum)


@pytest.mark.parametrize("count", [0, -1, True, None, "3", 3.0])
def test_long_decode_response_rejects_invalid_count(count):
    from gemma4_server_smoke import validate_long_decode_response

    response = {"choices": [{"message": {"content": "1, 2, 3\nCode word: PELICAN"}}]}

    with pytest.raises(RuntimeError, match="count.*positive integer"):
        validate_long_decode_response(response, count=count)


def test_gemma4_server_smoke_dry_run_exposes_measured_token_gate():
    result = run_helper(
        "google/gemma-4-E2B-it", "--mode", "basic", "--known-answer",
        "--long-decode", "--long-decode-count", "250",
        "--long-decode-min-completion-tokens", "1025", "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["long_decode_validation"] == {
        "count": 250,
        "min_completion_tokens": 1025,
        "required_finish_reason": "stop",
        "reject_truncation": True,
    }
    assert command_value(plan["server_command"], "--max-model-len") == "1536"
    assert plan["long_decode_request_payload"]["max_tokens"] == 1250
    assert "count from 1 to 250" in plan["long_decode_request_payload"]["messages"][0]["content"]
    assert "PELICAN" in plan["long_decode_request_payload"]["messages"][0]["content"]
    assert "known_answer_request_payload" in plan


def test_gemma4_server_smoke_dry_run_keeps_default_long_decode_without_token_floor():
    result = run_helper("google/gemma-4-E2B-it", "--long-decode", "--dry-run")

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["long_decode_validation"] == {
        "count": 150,
        "min_completion_tokens": None,
        "required_finish_reason": None,
        "reject_truncation": True,
    }
    assert plan["long_decode_request_payload"]["max_tokens"] == 800


def test_gemma4_server_smoke_rejects_token_floor_without_long_decode():
    result = run_helper(
        "google/gemma-4-E2B-it", "--long-decode-min-completion-tokens", "1025", "--dry-run",
    )

    assert result.returncode == 2
    assert "requires --long-decode" in result.stderr


@pytest.mark.parametrize("minimum", ["0", "-1"])
def test_gemma4_server_smoke_rejects_nonpositive_token_floor(minimum):
    result = run_helper(
        "google/gemma-4-E2B-it", "--long-decode",
        "--long-decode-min-completion-tokens", minimum, "--dry-run",
    )

    assert result.returncode == 2
    assert "--long-decode-min-completion-tokens must be positive" in result.stderr


@pytest.mark.parametrize("count", ["0", "-1"])
@pytest.mark.parametrize("extra", [[], ["--long-decode"]])
def test_gemma4_server_smoke_rejects_nonpositive_long_decode_count(count, extra):
    result = run_helper(
        "google/gemma-4-E2B-it", *extra, "--long-decode-count", count, "--dry-run",
    )

    assert result.returncode == 2
    assert "--long-decode-count must be positive" in result.stderr


@pytest.mark.parametrize("extra", [[], ["--max-model-len", "1024"]])
def test_gemma4_server_smoke_rejects_token_floor_above_request_budget(extra):
    result = run_helper(
        "google/gemma-4-E2B-it", "--long-decode",
        "--long-decode-min-completion-tokens", "1025", *extra, "--dry-run",
    )

    assert result.returncode == 2
    assert "minimum exceeds the long-decode request token budget" in result.stderr


def test_gemma4_server_smoke_rejects_noninteger_token_floor():
    result = run_helper(
        "google/gemma-4-E2B-it", "--long-decode",
        "--long-decode-min-completion-tokens", "1025.5", "--dry-run",
    )

    assert result.returncode == 2
    assert "invalid int value" in result.stderr


def run_helper(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HELPER), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPYCACHEPREFIX": "/tmp"},
        check=False,
    )


def command_value(command: list[str], flag: str) -> str:
    try:
        index = command.index(flag)
    except ValueError:
        raise AssertionError(f"{flag!r} not found in command: {command}") from None
    if index + 1 >= len(command):
        raise AssertionError(f"{flag!r} has no following value in command: {command}")
    return command[index + 1]


def _image_data_urls(mode: str) -> list[str]:
    content = multimodal_content(SimpleNamespace(mode=mode))
    urls = []
    for item in content:
        if item.get("type") == "image_url":
            image_url = item.get("image_url") or {}
            urls.append(image_url["url"])
    return urls


def test_gemma4_image_smoke_payloads_are_valid_pngs():
    for mode in ("image", "multi-image", "image-dynamic", "multimodal-tool"):
        for url in _image_data_urls(mode):
            prefix = "data:image/png;base64,"
            assert url.startswith(prefix)
            payload = base64.b64decode(url.removeprefix(prefix), validate=True)
            image = Image.open(BytesIO(payload))
            image.load()
            assert image.size[0] >= 1
            assert image.size[1] >= 1


def test_gemma4_multimodal_response_accepts_short_descriptive_caption():
    response = {
        "choices": [
            {
                "message": {
                    "content": "Solid bright blue color.",
                },
            },
        ],
    }

    assert validate_multimodal_response(response)["content"] == "Solid bright blue color."


def test_gemma4_server_smoke_uses_tighter_e2b_memory_default():
    result = run_helper("google/gemma-4-E2B-it", "--mode", "basic", "--dry-run")

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert command_value(plan["server_command"], "--gpu-memory-utilization") == "0.35"


def test_gemma4_server_smoke_keeps_26b_memory_default_and_allows_override():
    default_result = run_helper(
        "google/gemma-4-26B-A4B-it",
        "--mode",
        "basic",
        "--dry-run",
    )
    override_result = run_helper(
        "google/gemma-4-E2B-it",
        "--mode",
        "basic",
        "--gpu-memory-utilization",
        "0.5",
        "--dry-run",
    )

    assert default_result.returncode == 0, default_result.stderr
    assert override_result.returncode == 0, override_result.stderr
    default_plan = json.loads(default_result.stdout)
    override_plan = json.loads(override_result.stdout)
    assert command_value(default_plan["server_command"], "--gpu-memory-utilization") == "0.75"
    assert command_value(override_plan["server_command"], "--gpu-memory-utilization") == "0.5"


def test_gemma4_server_smoke_basic_plan_has_no_correctness_requests_by_default():
    result = run_helper("google/gemma-4-26B-A4B-it", "--mode", "basic", "--dry-run")

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert command_value(plan["server_command"], "--max-model-len") == "128"
    assert "known_answer_request_payload" not in plan
    assert "long_decode_request_payload" not in plan


def test_gemma4_server_smoke_plans_known_answer_and_long_decode_requests():
    result = run_helper(
        "google/gemma-4-26B-A4B-it",
        "--mode",
        "basic",
        "--known-answer",
        "--long-decode",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    command = plan["server_command"]
    # The long decode needs room for ~650 generated tokens, so it lifts the
    # 26B-A4B basic lane's 128-token default but keeps its batching cap.
    assert command_value(command, "--max-model-len") == "1024"
    assert command_value(command, "--max-num-batched-tokens") == "32"
    assert "--attention-backend" not in command

    known = plan["known_answer_request_payload"]
    assert known["temperature"] == 0.0
    assert known["max_tokens"] == 64
    assert "first ten prime numbers" in known["messages"][0]["content"]

    long_decode = plan["long_decode_request_payload"]
    assert long_decode["temperature"] == 0.0
    assert long_decode["max_tokens"] == 800
    assert "count from 1 to 150" in long_decode["messages"][0]["content"]
    assert "PELICAN" in long_decode["messages"][0]["content"]


def test_gemma4_server_smoke_wide_long_decode_sizes_the_26b_lane_past_its_window():
    result = run_helper(
        "google/gemma-4-26B-A4B-it",
        "--mode",
        "basic",
        "--long-decode",
        "--long-decode-count",
        "250",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    command = plan["server_command"]
    assert command_value(command, "--max-model-len") == "1536"
    assert command_value(command, "--max-num-batched-tokens") == "32"
    long_decode = plan["long_decode_request_payload"]
    assert long_decode["max_tokens"] == 1250
    assert "count from 1 to 250" in long_decode["messages"][0]["content"]


def test_gemma4_server_smoke_explicit_max_model_len_wins_over_long_decode_default():
    result = run_helper(
        "google/gemma-4-E2B-it",
        "--mode",
        "basic",
        "--long-decode",
        "--long-decode-count",
        "100",
        "--max-model-len",
        "2048",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert command_value(plan["server_command"], "--max-model-len") == "2048"
    content = plan["long_decode_request_payload"]["messages"][0]["content"]
    assert "count from 1 to 100" in content
