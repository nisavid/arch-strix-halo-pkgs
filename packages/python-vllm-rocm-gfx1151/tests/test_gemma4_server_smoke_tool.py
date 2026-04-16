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
VENDORED_TOOL_TEMPLATE = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/examples/tool_chat_template_gemma4.jinja"
)


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


def test_tool_dry_run_uses_vendored_chat_template_and_enables_tool_parser() -> None:
    plan = run_dry_run(
        "--mode",
        "tool",
        "--served-model-name",
        "gemma4-it",
        "/models/google/gemma-4-E2B-it",
    )

    command = plan["server_command"]
    assert "--tool-call-parser" in command
    assert "--reasoning-parser" in command
    assert "--enable-auto-tool-choice" in command
    assert "--chat-template" in command
    assert str(VENDORED_TOOL_TEMPLATE) in command
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
    assert str(VENDORED_TOOL_TEMPLATE) not in command


def test_vendored_tool_template_exists() -> None:
    assert VENDORED_TOOL_TEMPLATE.exists()


def test_docs_reference_server_smoke_tool() -> None:
    current_state = CURRENT_STATE.read_text()
    package_readme = PACKAGE_README.read_text()

    assert "tools/gemma4_server_smoke.py" in current_state
    assert "tools/gemma4_server_smoke.py" in package_readme
    assert '`--limit-mm-per-prompt {"image":0,"audio":0}`' in current_state
    assert '`--limit-mm-per-prompt {"image":0,"audio":0}`' in package_readme


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
