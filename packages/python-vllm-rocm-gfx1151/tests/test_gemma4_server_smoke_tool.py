from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SMOKE_TOOL = REPO_ROOT / "tools/gemma4_server_smoke.py"
CURRENT_STATE = REPO_ROOT / "docs/maintainers/current-state.md"
PACKAGE_README = REPO_ROOT / "packages/python-vllm-rocm-gfx1151/README.md"


def run_dry_run(*args: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, str(SMOKE_TOOL), "--dry-run", *args],
        check=True,
        capture_output=True,
        text=True,
        env={"PYTHONPYCACHEPREFIX": "/tmp"},
    )
    return json.loads(result.stdout)


def test_reasoning_dry_run_enables_reasoning_parser_and_thinking() -> None:
    plan = run_dry_run(
        "--mode",
        "reasoning",
        "--served-model-name",
        "gemma4-it",
        "/models/google/gemma-4-E2B-it",
    )

    command = plan["server_command"]
    assert command[:3] == [sys.executable, "-m", "vllm.entrypoints.openai.api_server"]
    assert "--reasoning-parser" in command
    assert "gemma4" in command
    assert "--tool-call-parser" not in command
    assert "--enable-auto-tool-choice" not in command
    assert int(command[command.index("--max-model-len") + 1]) == 1024
    assert json.loads(command[command.index("--limit-mm-per-prompt") + 1]) == {
        "image": 0,
        "audio": 0,
        "video": 0,
    }
    assert payload_max_tokens(plan) <= int(
        command[command.index("--max-model-len") + 1]
    )

    payload = plan["request_payload"]
    assert payload["model"] == "gemma4-it"
    assert payload["chat_template_kwargs"] == {"enable_thinking": True}
    assert payload["max_tokens"] > 0
    assert payload["skip_special_tokens"] is False
    assert "tools" not in payload


def test_tool_dry_run_uses_model_bundled_chat_template_and_enables_tool_parser(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "google-gemma-4-E2B-it"
    model_dir.mkdir()
    bundled_template = model_dir / "chat_template.jinja"
    bundled_template.write_text("{{ messages }}")

    plan = run_dry_run(
        "--mode",
        "tool",
        "--served-model-name",
        "gemma4-it",
        str(model_dir),
    )

    command = plan["server_command"]
    assert "--tool-call-parser" in command
    assert "--reasoning-parser" in command
    assert "--enable-auto-tool-choice" in command
    assert "--chat-template" in command
    assert str(bundled_template) in command
    assert int(command[command.index("--max-model-len") + 1]) == 1024

    payload = plan["request_payload"]
    assert payload["model"] == "gemma4-it"
    assert payload["tool_choice"] == "auto"
    assert payload["tools"][0]["function"]["name"] == "get_weather"
    assert payload["max_tokens"] > 0
    assert payload["skip_special_tokens"] is False
    assert payload_max_tokens(plan) <= int(
        command[command.index("--max-model-len") + 1]
    )


def test_tool_dry_run_prefers_model_bundled_chat_template(tmp_path: Path) -> None:
    model_dir = tmp_path / "google-gemma-4-26B-A4B-it"
    model_dir.mkdir()
    bundled_template = model_dir / "chat_template.jinja"
    bundled_template.write_text("{{ messages }}")

    plan = run_dry_run(
        "--mode",
        "tool",
        "--served-model-name",
        "gemma4-it",
        str(model_dir),
    )

    command = plan["server_command"]
    assert str(bundled_template) in command


def test_tool_dry_run_allows_chat_template_override(tmp_path: Path) -> None:
    template = tmp_path / "tool-chat-template.jinja"
    template.write_text("{{ messages }}")

    plan = run_dry_run(
        "--mode",
        "tool",
        "--chat-template",
        str(template),
        "--served-model-name",
        "gemma4-it",
        "/models/google/gemma-4-E2B-it",
    )

    command = plan["server_command"]
    assert str(template) in command


def test_basic_dry_run_forwards_max_num_batched_tokens() -> None:
    plan = run_dry_run(
        "--mode",
        "basic",
        "--max-num-batched-tokens",
        "32",
        "--served-model-name",
        "gemma4-it",
        "/models/google/gemma-4-26B-A4B-it",
    )

    command = plan["server_command"]
    assert "--max-num-batched-tokens" in command
    assert command[command.index("--max-num-batched-tokens") + 1] == "32"


def test_26b_a4b_basic_dry_run_defaults_to_constrained_text_only_lane() -> None:
    plan = run_dry_run(
        "--mode",
        "basic",
        "--served-model-name",
        "google/gemma-4-26B-A4B-it",
        "/models/google/gemma-4-26B-A4B-it",
    )

    command = plan["server_command"]
    assert int(command[command.index("--max-model-len") + 1]) == 128
    assert "--max-num-batched-tokens" in command
    assert command[command.index("--max-num-batched-tokens") + 1] == "32"
    assert json.loads(command[command.index("--limit-mm-per-prompt") + 1]) == {
        "image": 0,
        "audio": 0,
        "video": 0,
    }
    assert payload_max_tokens(plan) == 16


def test_tool_dry_run_without_template_errors_for_nonlocal_model() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SMOKE_TOOL),
            "--dry-run",
            "--mode",
            "tool",
            "--served-model-name",
            "gemma4-it",
            "/models/google/gemma-4-E2B-it",
        ],
        capture_output=True,
        text=True,
        env={"PYTHONPYCACHEPREFIX": "/tmp"},
    )

    assert result.returncode != 0
    assert (
        "--mode tool requires either --chat-template or a local model path that includes chat_template.jinja"
        in result.stderr
    )


def test_docs_reference_server_smoke_tool() -> None:
    current_state = CURRENT_STATE.read_text()
    package_readme = PACKAGE_README.read_text()

    assert "tools/gemma4_server_smoke.py" in current_state
    assert "tools/gemma4_server_smoke.py" in package_readme
    assert '`--limit-mm-per-prompt {"image":0,"audio":0,"video":0}`' in current_state
    assert '`--limit-mm-per-prompt {"image":0,"audio":0,"video":0}`' in package_readme
    assert "`ROCM_AITER_UNIFIED_ATTN`" in current_state
    assert "TRITON backend for Unquantized MoE" in current_state
    assert "`enforce_eager=True`" in current_state
    assert "TRITON unquantized MoE" in package_readme


def test_reasoning_validation_rejects_truncated_thought_block() -> None:
    module = load_smoke_module()

    response = {
        "choices": [
            {
                "finish_reason": "length",
                "message": {
                    "content": "thought\nHere is a partial chain of thought",
                    "reasoning": None,
                },
            }
        ]
    }

    try:
        module.validate_reasoning_response(response)
    except RuntimeError as exc:
        assert "truncated inside the Gemma 4 thought block" in str(exc)
    else:
        raise AssertionError("expected truncated reasoning response to fail")


def test_basic_validation_rejects_garbled_text() -> None:
    module = load_smoke_module()

    response = {
        "choices": [
            {
                "message": {
                    "content": "au로-ถed- \\اً way-\u200b**1-나 own",
                }
            }
        ]
    }

    try:
        module.validate_basic_response(response)
    except RuntimeError as exc:
        assert "unexpected non-ASCII content" in str(exc)
    else:
        raise AssertionError("expected garbled basic response to fail")


def payload_max_tokens(plan: dict[str, object]) -> int:
    payload = plan["request_payload"]
    assert isinstance(payload, dict)
    return int(payload["max_tokens"])


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("gemma4_server_smoke", SMOKE_TOOL)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
