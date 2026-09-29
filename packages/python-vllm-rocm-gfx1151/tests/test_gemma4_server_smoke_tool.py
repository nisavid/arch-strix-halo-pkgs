from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


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
    assert command[:5] == [
        sys.executable,
        "-m",
        "vllm.entrypoints.cli.main",
        "serve",
        "/models/google/gemma-4-E2B-it",
    ]
    assert "--model" not in command
    assert "vllm.entrypoints.openai.api_server" not in command
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


def test_26b_a4b_basic_dry_run_uses_extended_startup_timeout() -> None:
    plan = run_dry_run(
        "--mode",
        "basic",
        "--served-model-name",
        "google/gemma-4-26B-A4B-it",
        "/models/google/gemma-4-26B-A4B-it",
    )

    assert plan["startup_timeout"] == 420.0


def test_compiled_dry_run_omits_enforce_eager_and_forwards_kernel_flags() -> None:
    plan = run_dry_run(
        "--mode",
        "basic",
        "--execution-mode",
        "compiled",
        "--moe-backend",
        "aiter",
        "--async-scheduling",
        "--kv-cache-dtype",
        "fp8",
        "--no-enable-prefix-caching",
        "--max-num-seqs",
        "1",
        "--served-model-name",
        "google/gemma-4-26B-A4B-it",
        "/models/google/gemma-4-26B-A4B-it",
    )

    command = plan["server_command"]
    assert "--enforce-eager" not in command
    assert command[command.index("--moe-backend") + 1] == "aiter"
    assert "--async-scheduling" in command
    assert command[command.index("--kv-cache-dtype") + 1] == "fp8"
    assert "--no-enable-prefix-caching" in command
    assert command[command.index("--max-num-seqs") + 1] == "1"


def test_dry_run_forwards_attention_backend_probe() -> None:
    plan = run_dry_run(
        "--mode",
        "basic",
        "--attention-backend",
        "TRITON_ATTN",
        "--served-model-name",
        "gemma4-it",
        "/models/google/gemma-4-E2B-it",
    )

    command = plan["server_command"]
    assert command[command.index("--attention-backend") + 1] == "TRITON_ATTN"


def test_no_enforce_eager_alias_selects_compiled_execution() -> None:
    plan = run_dry_run(
        "--mode",
        "basic",
        "--no-enforce-eager",
        "--served-model-name",
        "gemma4-it",
        "/models/google/gemma-4-E2B-it",
    )

    assert plan["execution_mode"] == "compiled"
    assert "--enforce-eager" not in plan["server_command"]


def test_structured_dry_run_requests_json_schema() -> None:
    plan = run_dry_run(
        "--mode",
        "structured",
        "--served-model-name",
        "gemma4-it",
        "/models/google/gemma-4-E2B-it",
    )

    payload = plan["request_payload"]
    assert payload["response_format"]["type"] == "json_schema"
    schema = payload["response_format"]["json_schema"]["schema"]
    assert sorted(schema["properties"]) == ["answer", "topic"]
    # Pretty-printed JSON ran out of a 16-token budget mid-string.
    assert payload["max_tokens"] >= 128


def test_tool_thinking_dry_run_combines_tool_and_thinking(tmp_path: Path) -> None:
    model_dir = tmp_path / "google-gemma-4-E2B-it"
    model_dir.mkdir()
    (model_dir / "chat_template.jinja").write_text("{{ messages }}")

    plan = run_dry_run(
        "--mode",
        "tool-thinking",
        "--served-model-name",
        "gemma4-it",
        str(model_dir),
    )

    command = plan["server_command"]
    payload = plan["request_payload"]
    assert "--tool-call-parser" in command
    assert "--reasoning-parser" in command
    assert payload["chat_template_kwargs"] == {"enable_thinking": True}
    assert payload["tools"][0]["function"]["name"] == "get_weather"
    followup = plan["followup_request_payload"]
    assert "response_format" not in followup
    assert "tool_choice" not in followup


def test_full_feature_dry_run_moves_structured_output_to_followup(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "google-gemma-4-E2B-it"
    model_dir.mkdir()
    (model_dir / "chat_template.jinja").write_text("{{ messages }}")

    plan = run_dry_run(
        "--mode",
        "full-feature-text-only",
        "--served-model-name",
        "gemma4-it",
        str(model_dir),
    )

    command = plan["server_command"]
    assert "--tool-call-parser" in command
    assert "--reasoning-parser" in command
    assert "--enable-auto-tool-choice" in command

    # vLLM 0.30 wraps an auto tool call in the schema JSON when both share a
    # turn, so the tool-call turn carries no response_format.
    payload = plan["request_payload"]
    assert "response_format" not in payload
    assert payload["tool_choice"] == "auto"
    assert payload["chat_template_kwargs"] == {"enable_thinking": True}

    followup = plan["followup_request_payload"]
    assert followup["response_format"]["type"] == "json_schema"
    assert followup["tool_choice"] == "none"
    assert followup["chat_template_kwargs"] == {"enable_thinking": True}
    assert followup["tools"][0]["function"]["name"] == "get_weather"
    assert followup["messages"][-1]["role"] == "tool"
    # The follow-up carries the whole tool round trip (about 400 prompt
    # tokens on E2B), so its budget must leave that much room in the context.
    max_model_len = int(command[command.index("--max-model-len") + 1])
    assert followup["max_tokens"] + 400 <= max_model_len


def test_multimodal_dry_run_forwards_limits_and_processor_kwargs() -> None:
    plan = run_dry_run(
        "--mode",
        "image",
        "--limit-mm-per-prompt",
        '{"image":1,"audio":0,"video":0}',
        "--processor-kwargs",
        '{"do_pan_and_scan":true}',
        "--served-model-name",
        "gemma4-it",
        "/models/google/gemma-4-E2B-it",
    )

    command = plan["server_command"]
    payload = plan["request_payload"]
    assert json.loads(command[command.index("--limit-mm-per-prompt") + 1]) == {
        "image": 1,
        "audio": 0,
        "video": 0,
    }
    assert json.loads(command[command.index("--mm-processor-kwargs") + 1]) == {
        "do_pan_and_scan": True,
    }
    content = payload["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"


def test_benchmark_lite_dry_run_disables_prefix_caching() -> None:
    plan = run_dry_run(
        "--mode",
        "benchmark-lite",
        "--served-model-name",
        "gemma4-it",
        "/models/google/gemma-4-E2B-it",
    )

    assert "--no-enable-prefix-caching" in plan["server_command"]
    # benchmark-lite shares the basic five-word check, so it needs the same
    # budget; 8 tokens cut "Vast, blue, endless, mysterious, powerful." short.
    basic_plan = run_dry_run(
        "--mode",
        "basic",
        "--served-model-name",
        "gemma4-it",
        "/models/google/gemma-4-E2B-it",
    )
    assert payload_max_tokens(plan) == payload_max_tokens(basic_plan)


def test_terminate_process_kills_spawned_child_process_group(tmp_path: Path) -> None:
    module = load_smoke_module()
    child_pid_file = tmp_path / "child.pid"
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "import subprocess, sys, time; "
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)']); "
                "Path(sys.argv[1]).write_text(str(child.pid)); "
                "time.sleep(600)"
            ),
            str(child_pid_file),
        ],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    child_pid = wait_for_child_pid(child_pid_file)

    try:
        module.terminate_process(process)
        assert process.poll() is not None
        wait_for_process_exit(child_pid)
    finally:
        force_kill_pid(process.pid)
        force_kill_pid(child_pid)


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


# Responses captured from the Gemma 4 E2B server lanes on vLLM 0.30, cut down
# to the fields the validators read.
E2B_BASIC_RESPONSE = {
    "choices": [
        {
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": "Vast, blue, endless, mysterious, powerful.",
            },
        }
    ]
}
E2B_BENCHMARK_LITE_8_TOKEN_RESPONSE = {
    "choices": [
        {
            "finish_reason": "length",
            "message": {
                "role": "assistant",
                "content": "Vast, blue, endless, mysterious",
            },
        }
    ]
}
E2B_STRUCTURED_16_TOKEN_RESPONSE = {
    "choices": [
        {
            "finish_reason": "length",
            "message": {
                "role": "assistant",
                "content": '{\n  "topic": "The Ocean",\n  "answer": "',
            },
        }
    ]
}
E2B_TOOL_INITIAL_RESPONSE = {
    "choices": [
        {
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "chatcmpl-tool-a82cf79825954dbb",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"location": "Tokyo"}',
                        },
                    }
                ],
            },
        }
    ]
}
E2B_TOOL_FOLLOWUP_RESPONSE = {
    "choices": [
        {
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": (
                    "The weather in Tokyo today is partly cloudy with a "
                    "temperature of 22 degrees Celsius."
                ),
            },
        }
    ]
}
# full-feature-text-only with response_format on the tool-call turn: xgrammar
# wrapped the tool call in the schema JSON and escaped its arguments.
E2B_FULL_FEATURE_SCHEMA_TOOL_CALL_RESPONSE = {
    "choices": [
        {
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": '{\n  "topic": "get_weather",\n  "answer": "',
                "tool_calls": [
                    {
                        "id": "chatcmpl-tool-ab3f66313d3b779a",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": r'{"location": "\\\"Tokyo\\\""}',
                        },
                    }
                ],
            },
        }
    ]
}
# The follow-up to that turn continued the half-written JSON.
E2B_FULL_FEATURE_CONTINUED_JSON_FOLLOWUP_RESPONSE = {
    "choices": [
        {
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": (
                    '  "condition": "Partly cloudy",\n  "temperature": 22,\n'
                    '  "unit": "celsius"\n}'
                ),
            },
        }
    ]
}


def with_choice(response: dict[str, object], **changes: object) -> dict[str, object]:
    choice = dict(response["choices"][0])
    message = dict(choice["message"])
    for key, value in changes.items():
        if key == "finish_reason":
            choice[key] = value
        else:
            message[key] = value
    choice["message"] = message
    return {"choices": [choice]}


def test_basic_validation_accepts_captured_five_word_answer() -> None:
    module = load_smoke_module()

    message = module.validate_basic_response(E2B_BASIC_RESPONSE)

    assert message["content"] == "Vast, blue, endless, mysterious, powerful."


def test_basic_validation_reports_max_tokens_truncation_before_word_count() -> None:
    module = load_smoke_module()

    with pytest.raises(RuntimeError, match="truncated at max_tokens budget"):
        module.validate_basic_response(E2B_BENCHMARK_LITE_8_TOKEN_RESPONSE)


def test_structured_validation_reports_max_tokens_truncation() -> None:
    module = load_smoke_module()

    with pytest.raises(RuntimeError, match="structured response truncated at max_tokens"):
        module.validate_structured_response(E2B_STRUCTURED_16_TOKEN_RESPONSE)


def test_tool_validation_accepts_captured_tokyo_call() -> None:
    module = load_smoke_module()

    message = module.validate_tool_response(E2B_TOOL_INITIAL_RESPONSE)

    assert message["tool_calls"][0]["function"]["name"] == "get_weather"


def test_tool_validation_rejects_escaped_location_argument() -> None:
    module = load_smoke_module()
    arguments = E2B_FULL_FEATURE_SCHEMA_TOOL_CALL_RESPONSE["choices"][0]["message"][
        "tool_calls"
    ][0]["function"]["arguments"]
    assert json.loads(arguments) == {"location": '\\"Tokyo\\"'}

    with pytest.raises(RuntimeError, match="did not name location 'Tokyo'"):
        module.validate_tool_response(E2B_FULL_FEATURE_SCHEMA_TOOL_CALL_RESPONSE)


def test_tool_validation_rejects_non_json_arguments() -> None:
    module = load_smoke_module()
    response = json.loads(json.dumps(E2B_TOOL_INITIAL_RESPONSE))
    response["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = (
        "location=Tokyo"
    )

    with pytest.raises(RuntimeError, match="tool call arguments were not JSON"):
        module.validate_tool_response(response)


def test_tool_followup_validation_accepts_captured_sentence_answer() -> None:
    module = load_smoke_module()

    # Fifteen words: the old exact-five-word check rejected this answer.
    message = module.validate_tool_followup_response(E2B_TOOL_FOLLOWUP_RESPONSE)

    assert "22 degrees" in message["content"]


def test_tool_followup_validation_rejects_answer_without_tool_result() -> None:
    module = load_smoke_module()
    response = with_choice(
        E2B_TOOL_FOLLOWUP_RESPONSE,
        content="I could not find the weather for Tokyo.",
    )

    with pytest.raises(RuntimeError, match="did not use the tool result"):
        module.validate_tool_followup_response(response)


def test_tool_followup_validation_rejects_another_tool_call() -> None:
    module = load_smoke_module()
    response = with_choice(
        E2B_TOOL_FOLLOWUP_RESPONSE,
        finish_reason="tool_calls",
        tool_calls=E2B_TOOL_INITIAL_RESPONSE["choices"][0]["message"]["tool_calls"],
    )

    with pytest.raises(RuntimeError, match="called a tool instead of answering"):
        module.validate_tool_followup_response(response)


def test_tool_followup_validation_rejects_truncated_answer() -> None:
    module = load_smoke_module()
    response = with_choice(
        E2B_TOOL_FOLLOWUP_RESPONSE,
        finish_reason="length",
        content="The weather in Tokyo today is partly cloudy",
    )

    with pytest.raises(RuntimeError, match="truncated at max_tokens budget"):
        module.validate_tool_followup_response(response)


def test_tool_followup_validation_rejects_non_ascii_answer() -> None:
    module = load_smoke_module()
    response = with_choice(
        E2B_TOOL_FOLLOWUP_RESPONSE,
        content="Tokyo: 22°C, 로 partly cloudy",
    )

    with pytest.raises(RuntimeError, match="unexpected non-ASCII content"):
        module.validate_tool_followup_response(response)


def test_structured_tool_followup_validation_accepts_schema_answer() -> None:
    module = load_smoke_module()
    response = with_choice(
        E2B_TOOL_FOLLOWUP_RESPONSE,
        content=(
            '{\n  "topic": "Weather in Tokyo",\n'
            '  "answer": "Partly cloudy, 22 degrees Celsius."\n}'
        ),
    )

    message = module.validate_structured_tool_followup_response(response)

    assert json.loads(message["content"])["topic"] == "Weather in Tokyo"


def test_structured_tool_followup_validation_rejects_continued_json() -> None:
    module = load_smoke_module()

    with pytest.raises(RuntimeError, match="structured response was not JSON"):
        module.validate_structured_tool_followup_response(
            E2B_FULL_FEATURE_CONTINUED_JSON_FOLLOWUP_RESPONSE
        )


def test_structured_tool_followup_validation_rejects_answer_without_tool_result() -> None:
    module = load_smoke_module()
    response = with_choice(
        E2B_TOOL_FOLLOWUP_RESPONSE,
        content='{"topic": "Tokyo", "answer": "Check a forecast service."}',
    )

    with pytest.raises(RuntimeError, match="did not use the tool result"):
        module.validate_structured_tool_followup_response(response)


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


def wait_for_child_pid(path: Path) -> int:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if path.exists():
            return int(path.read_text().strip())
        time.sleep(0.05)
    raise AssertionError("timed out waiting for child pid file")


def wait_for_process_exit(pid: int) -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not process_exists(pid):
            return
        time.sleep(0.05)
    raise AssertionError(f"expected pid {pid} to exit")


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def force_kill_pid(pid: int) -> None:
    if pid <= 0 or not process_exists(pid):
        return
    os.kill(pid, 9)
