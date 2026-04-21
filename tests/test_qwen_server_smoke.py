from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "tools/qwen_server_smoke.py"


def run_helper(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HELPER), *args],
        capture_output=True,
        text=True,
        env={"PYTHONPYCACHEPREFIX": "/tmp"},
    )


def dry_run(mode: str, *args: str) -> dict[str, object]:
    result = run_helper("Qwen/Qwen3.6-35B-A3B", "--mode", mode, "--dry-run", *args)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def command_value(command: list[str], flag: str) -> str:
    return command[command.index(flag) + 1]


def test_qwen_server_smoke_help_lists_modes():
    result = run_helper("--help")

    assert result.returncode == 0
    assert "reasoning-disabled" in result.stdout
    assert "media-embedding" in result.stdout


def test_qwen_server_smoke_dry_run_uses_compact_json_and_defaults():
    plan = dry_run("reasoning")
    command = plan["server_command"]

    assert command[:3] == [sys.executable, "-m", "vllm.entrypoints.openai.api_server"]
    assert command_value(command, "--gpu-memory-utilization") == "0.9"
    assert command_value(command, "--max-model-len") == "1024"
    assert command_value(command, "--max-num-batched-tokens") == "32"
    assert command_value(command, "--limit-mm-per-prompt") == (
        '{"audio":0,"image":0,"video":0}'
    )
    assert "--enforce-eager" in command
    assert "--trust-remote-code" in command
    assert "--disable-log-stats" in command
    assert command_value(command, "--reasoning-parser") == "qwen3"
    assert plan["startup_timeout"] == 420.0


def test_qwen_server_smoke_mode_specific_server_args():
    disabled_command = dry_run("reasoning-disabled")["server_command"]
    mtp_command = dry_run("mtp")["server_command"]
    tool_command = dry_run("tool")["server_command"]
    benchmark_command = dry_run("benchmark-lite")["server_command"]
    selectors_command = dry_run("advanced-selectors")["server_command"]
    media_command = dry_run("media-embedding")["server_command"]

    assert command_value(disabled_command, "--default-chat-template-kwargs") == (
        '{"enable_thinking":false}'
    )
    assert command_value(mtp_command, "--speculative-config") == (
        '{"method":"mtp","num_speculative_tokens":2}'
    )
    assert "--speculative-tokens" not in mtp_command
    assert "--enable-auto-tool-choice" in tool_command
    assert command_value(tool_command, "--tool-call-parser") == "qwen3_coder"
    assert "--no-enable-prefix-caching" in benchmark_command
    assert "--async-scheduling" in benchmark_command
    assert command_value(selectors_command, "--max-num-batched-tokens") == "8192"
    assert command_value(selectors_command, "--max-num-seqs") == "256"
    assert command_value(media_command, "--mm-processor-kwargs") == (
        '{"videos_kwargs":{"size":{"longest_edge":469762048,"shortest_edge":4096}}}'
    )
    assert command_value(media_command, "--limit-mm-per-prompt") == (
        '{"audio":0,"image":{"count":1,"height":2,"width":2},"video":0}'
    )


def test_qwen_server_smoke_draft_model_uses_draft_speculative_config():
    plan = dry_run("reasoning", "--draft-model", "Qwen/Qwen3.5-0.8B")
    command = plan["server_command"]

    assert plan["draft_model"] == "Qwen/Qwen3.5-0.8B"
    assert command_value(command, "--speculative-config") == (
        '{"method":"draft_model","model":"Qwen/Qwen3.5-0.8B","num_speculative_tokens":2}'
    )


def test_qwen_server_smoke_payload_modes():
    reasoning = dry_run("reasoning")["request_payload"]
    disabled = dry_run("reasoning-disabled")["request_payload"]
    mtp = dry_run("mtp")["request_payload"]
    tool = dry_run("tool")
    benchmark = dry_run("benchmark-lite")["request_payload"]
    long_context = dry_run("long-context-reduced")["request_payload"]
    media = dry_run("media-embedding")["request_payload"]

    assert reasoning["chat_template_kwargs"] == {"enable_thinking": True}
    assert disabled["chat_template_kwargs"] == {"enable_thinking": False}
    assert mtp["chat_template_kwargs"] == {"enable_thinking": True}
    assert tool["request_payload"]["tool_choice"] == "auto"
    assert tool["followup_request_payload"]["messages"][1]["tool_calls"][0][
        "function"
    ]["name"] == "get_weather"
    assert benchmark["max_tokens"] == 8
    assert "needle" in long_context["messages"][0]["content"].lower()
    assert media["messages"][0]["content"][1]["type"] == "image_url"


def test_qwen_server_smoke_invalid_json_fails():
    result = run_helper(
        "Qwen/Qwen3.6-35B-A3B",
        "--mode",
        "reasoning",
        "--limit-mm-per-prompt",
        "{bad-json",
        "--dry-run",
    )

    assert result.returncode != 0
    assert "--limit-mm-per-prompt must be valid JSON" in result.stderr
