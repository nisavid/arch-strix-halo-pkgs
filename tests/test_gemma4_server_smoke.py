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


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "tools/gemma4_server_smoke.py"
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from gemma4_server_smoke import multimodal_content, validate_multimodal_response


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
