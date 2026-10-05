from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys

import pytest


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def test_basic_response_accepts_the_selected_answer():
    from granite_server_smoke import validate_granite_response

    message = {"role": "assistant", "content": "12"}
    response = {"choices": [{"message": message, "finish_reason": "stop"}]}

    assert validate_granite_response("basic", response) == message


def test_basic_response_rejects_an_explicit_error_despite_the_selected_answer():
    from granite_server_smoke import validate_granite_response

    response = {
        "error": {"message": "request failed"},
        "choices": [{"message": {"role": "assistant", "content": "12"}, "finish_reason": "stop"}],
    }

    with pytest.raises(RuntimeError, match="error"):
        validate_granite_response("basic", response)


def test_basic_response_rejects_a_refusal_despite_the_selected_answer():
    from granite_server_smoke import validate_granite_response

    response = {"choices": [{
        "message": {"role": "assistant", "content": "12", "refusal": "request refused"},
        "finish_reason": "stop",
    }]}

    with pytest.raises(RuntimeError, match="refusal"):
        validate_granite_response("basic", response)


@pytest.fixture(params=[
    ("basic", "12", "stop"),
    ("tool", None, "tool_calls"),
    ("structured", '{"topic":"ocean","answer":"blue"}', "stop"),
])
def selected_fixture_response(request):
    mode, content, finish = request.param
    message = {"role": "assistant", "content": content}
    if mode == "tool":
        message["tool_calls"] = [{
            "id": "call_weather", "type": "function",
            "function": {"name": "get_weather", "arguments": '{"location":"Tokyo","unit":"celsius"}'},
        }]
    return mode, {"choices": [{"message": message, "finish_reason": finish}]}


@pytest.mark.parametrize("field,value", [
    ("error", {"message": "request failed"}), ("error", ""), ("error", False), ("error", {}),
    ("refusal", "request refused"), ("refusal", ""), ("refusal", False), ("refusal", {}),
])
def test_selected_results_reject_nonnull_error_or_refusal(selected_fixture_response, field, value):
    from granite_server_smoke import validate_granite_response

    mode, response = selected_fixture_response
    target = response if field == "error" else response["choices"][0]["message"]
    target[field] = value

    with pytest.raises(RuntimeError, match=field):
        validate_granite_response(mode, response)


def test_selected_results_accept_explicit_null_error_and_refusal(selected_fixture_response):
    from granite_server_smoke import validate_granite_response

    mode, response = selected_fixture_response
    message = response["choices"][0]["message"]
    response["error"] = None
    message["refusal"] = None

    assert validate_granite_response(mode, response) == message


@pytest.mark.parametrize("content", [" 12", "12\n", "\t12\t", " \n12\t"])
def test_basic_response_requires_the_literal_selected_answer(content):
    from granite_server_smoke import validate_granite_response

    response = {"choices": [{
        "message": {"role": "assistant", "content": content}, "finish_reason": "stop",
    }]}

    with pytest.raises(RuntimeError, match="exactly 12"):
        validate_granite_response("basic", response)


@pytest.mark.parametrize("response", [
    None, [], {}, {"choices": []}, {"choices": "bad"},
    {"choices": [None]}, {"choices": [{"message": None}]},
    {"choices": [{"message": {"role": "user", "content": "12"}, "finish_reason": "stop"}]},
    {"choices": [{"message": {"role": "assistant", "content": 12}, "finish_reason": "stop"}]},
    {"choices": [{"message": {"role": "assistant", "content": "12"}, "finish_reason": "length"}]},
    {"choices": [{"message": {"role": "assistant", "content": "13"}, "finish_reason": "stop"}]},
    {"choices": [{"message": {"role": "assistant", "content": "12", "tool_calls": [{}]}, "finish_reason": "stop"}]},
    {"choices": [{"message": {"role": "assistant", "content": "12"}, "finish_reason": "stop"}] * 2},
])
def test_basic_response_rejects_malformed_or_unselected_results(response):
    from granite_server_smoke import validate_granite_response

    with pytest.raises(RuntimeError, match="Granite"):
        validate_granite_response("basic", response)


def test_unknown_fixture_mode_is_rejected():
    from granite_server_smoke import validate_granite_response

    with pytest.raises(RuntimeError, match="mode"):
        validate_granite_response("unselected", {})


def test_tool_response_accepts_one_parsed_weather_call():
    from granite_server_smoke import validate_granite_response

    message = {
        "role": "assistant", "content": None,
        "tool_calls": [{
            "id": "call_weather", "type": "function",
            "function": {"name": "get_weather", "arguments": '{"location":"Tokyo","unit":"celsius"}'},
        }],
    }
    response = {"choices": [{"message": message, "finish_reason": "tool_calls"}]}

    assert validate_granite_response("tool", response) == message


@pytest.mark.parametrize("calls,content,finish", [
    (None, None, "tool_calls"), ([], None, "tool_calls"), ([None], None, "tool_calls"),
    ([{"id": "c", "type": "function", "function": None}], None, "tool_calls"),
    ([{"id": "", "type": "function", "function": {"name": "get_weather", "arguments": '{"location":"Tokyo","unit":"celsius"}'}}], None, "tool_calls"),
    ([{"id": "c", "type": "function", "function": {"name": "get_weather", "arguments": '{"location":"Tokyo","unit":"celsius"}'}}] * 2, None, "tool_calls"),
    ([{"id": "c", "type": "function", "function": {"name": "get_weather", "arguments": '{"location":"Tokyo","unit":"celsius"}'}}], "<|tool_call|>raw text", "tool_calls"),
    ([{"id": "c", "type": "function", "function": {"name": "get_weather", "arguments": '{"location":"Tokyo","unit":"celsius"}'}}], None, "stop"),
    ([{"id": "c", "type": "other", "function": {"name": "get_weather", "arguments": '{"location":"Tokyo","unit":"celsius"}'}}], None, "tool_calls"),
    ([{"id": "c", "type": "function", "function": {"name": "other", "arguments": '{"location":"Tokyo","unit":"celsius"}'}}], None, "tool_calls"),
])
def test_tool_response_rejects_missing_or_unparsed_weather_call(calls, content, finish):
    from granite_server_smoke import validate_granite_response

    response = {"choices": [{
        "message": {"role": "assistant", "content": content, "tool_calls": calls},
        "finish_reason": finish,
    }]}

    with pytest.raises(RuntimeError, match="Granite"):
        validate_granite_response("tool", response)


def test_structured_response_accepts_only_the_selected_object():
    from granite_server_smoke import validate_granite_response

    message = {"role": "assistant", "content": '{"answer":"blue","topic":"ocean"}'}
    response = {"choices": [{"message": message, "finish_reason": "stop"}]}

    assert validate_granite_response("structured", response) == message


@pytest.mark.parametrize("content", [
    None, {}, "not JSON", "```json\n{\"topic\":\"ocean\",\"answer\":\"blue\"}\n```",
    '[{"topic":"ocean","answer":"blue"}]', '{"topic":"ocean","answer":12}',
    '{"topic":"ocean","answer":"green"}', '{"topic":"ocean"}',
    '{"topic":"ocean","answer":"blue","extra":null}',
    '{"topic":"river","topic":"ocean","answer":"blue"}',
    '{"topic":"ocean","answer":NaN}',
])
def test_structured_response_rejects_other_or_ambiguous_objects(content):
    from granite_server_smoke import validate_granite_response

    response = {"choices": [{
        "message": {"role": "assistant", "content": content}, "finish_reason": "stop",
    }]}

    with pytest.raises(RuntimeError, match="Granite"):
        validate_granite_response("structured", response)


@pytest.mark.parametrize("finish,calls", [("length", None), ("tool_calls", []), (None, None), ("stop", [{}])])
def test_structured_response_requires_stop_without_tool_calls(finish, calls):
    from granite_server_smoke import validate_granite_response

    response = {"choices": [{
        "message": {"role": "assistant", "content": '{"topic":"ocean","answer":"blue"}', "tool_calls": calls},
        "finish_reason": finish,
    }]}

    with pytest.raises(RuntimeError, match="Granite"):
        validate_granite_response("structured", response)


@pytest.mark.parametrize("arguments", [
    None, {"location": "Tokyo", "unit": "celsius"}, "not JSON", "[]", "null",
    '{"location":"Tokyo","unit":"fahrenheit"}', '{"location":"Osaka","unit":"celsius"}',
    '{"location":"Tokyo","unit":"celsius","extra":true}',
    '{"location":"Osaka","location":"Tokyo","unit":"celsius"}',
    '{"location":"Tokyo","unit":NaN}',
])
def test_tool_response_rejects_malformed_or_different_arguments(arguments):
    from granite_server_smoke import validate_granite_response

    response = {"choices": [{
        "message": {"role": "assistant", "tool_calls": [{
            "id": "c", "type": "function",
            "function": {"name": "get_weather", "arguments": arguments},
        }]},
        "finish_reason": "tool_calls",
    }]}

    with pytest.raises(RuntimeError, match="Granite"):
        validate_granite_response("tool", response)


@pytest.mark.parametrize("backend", ["ROCm AITER", "TRITON", "BATCHED_TRITON"])
def test_moe_parser_returns_the_affirmatively_selected_backend(backend):
    from granite_server_smoke import parse_selected_moe_backend

    log = f"INFO [unquantized.py:1] Using {backend} Unquantized MoE backend out of potential backends: ['ROCm AITER', 'TRITON', 'BATCHED_TRITON'].\n"

    assert parse_selected_moe_backend(log) == backend


@pytest.mark.parametrize("log", [
    None, "", "Potential backends: ['TRITON']", "TRITON is not supported",
    "Using  Unquantized MoE backend out of potential backends: ['TRITON'].",
    "Not Using TRITON Unquantized MoE backend out of potential backends: ['TRITON'].",
    "Using TRITON Unquantized MoE backend out of potential backends: ['TRITON'].\nUsing ROCm AITER Unquantized MoE backend out of potential backends: ['ROCm AITER'].",
])
def test_moe_parser_rejects_missing_negative_or_conflicting_evidence(log):
    from granite_server_smoke import parse_selected_moe_backend

    with pytest.raises(RuntimeError, match="MoE"):
        parse_selected_moe_backend(log)


def test_moe_parser_accepts_repeated_consistent_selection_without_forcing_a_backend():
    from granite_server_smoke import parse_selected_moe_backend

    line = "Using ROCm AITER Unquantized MoE backend out of potential backends: ['TRITON', 'ROCm AITER'].\n"

    assert parse_selected_moe_backend(line * 2) == "ROCm AITER"


def test_moe_parser_rejects_a_bracketed_negative_diagnostic():
    from granite_server_smoke import parse_selected_moe_backend

    log = "[not selected] Using TRITON Unquantized MoE backend out of potential backends: ['TRITON']."

    with pytest.raises(RuntimeError, match="no affirmative"):
        parse_selected_moe_backend(log)


@pytest.mark.parametrize("prefix", [
    "INFO [not selected] ", "[unquantized.py:1] ", "not INFO [unquantized.py:1] ",
    "WARNING [unquantized.py:1] ", "INFO [diagnostic.py:1] ",
])
def test_moe_parser_does_not_treat_arbitrary_metadata_as_an_oracle_record(prefix):
    from granite_server_smoke import parse_selected_moe_backend

    log = prefix + "Using TRITON Unquantized MoE backend out of potential backends: ['TRITON']."

    with pytest.raises(RuntimeError, match="no affirmative"):
        parse_selected_moe_backend(log)


@pytest.mark.parametrize("location", ["unquantized.py:1", "model_executor/.../oracle/unquantized.py:42"])
def test_moe_parser_accepts_timestamped_pinned_vllm_info_records(location):
    from granite_server_smoke import parse_selected_moe_backend

    log = f"INFO 10-05 12:34:56 [{location}] Using TRITON Unquantized MoE backend out of potential backends: ['TRITON']."

    assert parse_selected_moe_backend(log) == "TRITON"


@pytest.mark.parametrize("prefix", [
    "(EngineCore_DP0 pid=42) INFO 10-05 12:34:56 [unquantized.py:1] ",
    "\x1b[1;36m(Worker_TP0 pid=42)\x1b[0m \x1b[32mINFO\x1b[0m "
    "\x1b[90m10-05 12:34:56\x1b[0m \x1b[90m[unquantized.py:1]\x1b[0m ",
])
def test_moe_parser_accepts_pinned_vllm_process_and_color_formatting(prefix):
    from granite_server_smoke import parse_selected_moe_backend

    log = prefix + "Using TRITON Unquantized MoE backend out of potential backends: ['TRITON']."

    assert parse_selected_moe_backend(log) == "TRITON"


@pytest.mark.parametrize("separator", [" ", "\n"])
def test_moe_parser_does_not_hide_a_second_conflicting_oracle_record(separator):
    from granite_server_smoke import parse_selected_moe_backend

    first = "INFO [unquantized.py:1] Using TRITON Unquantized MoE backend out of potential backends: ['TRITON']."
    second = "INFO [unquantized.py:1] Using ROCm AITER Unquantized MoE backend out of potential backends: ['ROCm AITER']."

    with pytest.raises(RuntimeError, match="conflicting"):
        parse_selected_moe_backend(first + separator + second)


def test_moe_parser_accepts_consistent_oracle_records_on_one_line():
    from granite_server_smoke import parse_selected_moe_backend

    record = "INFO [unquantized.py:1] Using TRITON Unquantized MoE backend out of potential backends: ['TRITON']."

    assert parse_selected_moe_backend(record + " " + record) == "TRITON"


@pytest.mark.parametrize("log", [
    "WARNING [diagnostic.py:1] Not selected. Using TRITON Unquantized MoE backend out of potential backends: ['TRITON'].",
    "WARNING [diagnostic.py:1] Selection rejected. INFO [unquantized.py:1] Using TRITON Unquantized MoE backend out of potential backends: ['TRITON'].",
    "Using TRITON Unquantized MoE backend out of potential backends: ['TRITON']. (not selected)",
    "INFO [unquantized.py:1] Using TRITON Unquantized MoE backend out of potential backends: ['TRITON']. Selection rejected.",
])
def test_moe_parser_rejects_selection_phrases_inside_diagnostic_lines(log):
    from granite_server_smoke import parse_selected_moe_backend

    with pytest.raises(RuntimeError, match="no affirmative"):
        parse_selected_moe_backend(log)


@pytest.mark.parametrize("diagnostic", [
    "WARNING [diagnostic.py:1] Not selected. Using TRITON Unquantized MoE backend out of potential backends: ['TRITON'].",
    "WARNING [diagnostic.py:1] Selection rejected. INFO [unquantized.py:1] Using TRITON Unquantized MoE backend out of potential backends: ['TRITON'].",
    "Using TRITON Unquantized MoE backend out of potential backends: ['TRITON']. (not selected)",
    "INFO [unquantized.py:1] Using TRITON Unquantized MoE backend out of potential backends: ['TRITON']. Selection rejected.",
])
@pytest.mark.parametrize("diagnostic_first", [False, True])
def test_moe_parser_does_not_confuse_diagnostics_with_a_genuine_selection(diagnostic, diagnostic_first):
    from granite_server_smoke import parse_selected_moe_backend

    genuine = "INFO [unquantized.py:1] Using ROCm AITER Unquantized MoE backend out of potential backends: ['ROCm AITER']."
    lines = [diagnostic, genuine] if diagnostic_first else [genuine, diagnostic]

    assert parse_selected_moe_backend("\n".join(lines)) == "ROCm AITER"


def test_moe_parser_rejects_concatenated_conflicting_messages_without_logger_prefixes():
    from granite_server_smoke import parse_selected_moe_backend

    log = "Using TRITON Unquantized MoE backend out of potential backends: ['TRITON']. Using ROCm AITER Unquantized MoE backend out of potential backends: ['ROCm AITER']."

    with pytest.raises(RuntimeError, match="conflicting"):
        parse_selected_moe_backend(log)


def test_retained_fixture_corpus_matches_the_selected_response_contracts():
    from granite_server_smoke import validate_granite_response

    corpus = json.loads((TOOLS_DIR.parent / "inference/fixtures/granite-3.1-1b-a400m-instruct.json").read_text())
    assert corpus["model_id"] == "ibm-granite/granite-3.1-1b-a400m-instruct"
    assert corpus["revision"] == "0da7a48b0276d500ce5922fd2b33944091fc6c09"
    assert [fixture["mode"] for fixture in corpus["fixtures"]] == ["basic", "tool", "structured"]
    for fixture in corpus["fixtures"]:
        request, expected = fixture["request"], fixture["expected"]
        assert request["model"] == corpus["model_id"]
        assert request["stream"] is False
        assert request["temperature"] == 0 and request["n"] == 1
        assert [message["role"] for message in request["messages"]] == ["system", "user"]
        message = {"role": "assistant"}
        if fixture["mode"] == "tool":
            assert "response_format" not in request
            assert request["tool_choice"] == "auto"
            assert request["tools"][0]["function"]["name"] == expected["function"]
            message["tool_calls"] = [{
                "id": "fixture_call", "type": "function",
                "function": {"name": expected["function"], "arguments": json.dumps(expected["arguments"])},
            }]
        elif fixture["mode"] == "structured":
            assert "tools" not in request
            schema = request["response_format"]["json_schema"]["schema"]
            assert schema["additionalProperties"] is False
            assert set(schema["required"]) == set(expected["object"])
            message["content"] = json.dumps(expected["object"])
        else:
            message["content"] = expected["content"]
        response = {"choices": [{"message": message, "finish_reason": expected["finish_reason"]}]}
        assert validate_granite_response(fixture["mode"], response) == message


def _run_preparation_cli(*arguments):
    return subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(TOOLS_DIR / "granite_server_smoke.py"), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("mode", ["basic", "tool", "structured"])
def test_preparation_cli_reports_unverified_inputs_and_preserves_the_corpus_request(mode):
    corpus = json.loads((TOOLS_DIR.parent / "inference/fixtures/granite-3.1-1b-a400m-instruct.json").read_text())
    expected = next(fixture["request"] for fixture in corpus["fixtures"] if fixture["mode"] == mode)

    result = _run_preparation_cli("proposed-model", "--mode", mode, "--dry-run")

    assert result.returncode == 0, result.stderr
    preparation = json.loads(result.stdout)
    assert preparation == {
        "mode": mode,
        "status": "preparation-only",
        "runtime_ready": False,
        "model": {"value": "proposed-model", "status": "proposed/unverified"},
        "corpus": {
            "repo_id": "ibm-granite/granite-3.1-1b-a400m-instruct",
            "revision": "0da7a48b0276d500ce5922fd2b33944091fc6c09",
            "sha256": "cfc8740cdf71455fea91064caf3c8545763344c9b71803abf115323a6e98d094",
        },
        "request": expected,
        "unresolved_requirements": [
            "reviewed fit/fault-stop method",
            "selected Granite operating envelope",
            "qualifying immutable C subject",
        ],
    }


def test_preparation_cli_rejects_execution_without_dry_run():
    result = _run_preparation_cli("proposed-model", "--mode", "basic")

    assert result.returncode == 2
    assert result.stdout == ""
    assert "requires --dry-run" in result.stderr
    assert "execution is not available" in result.stderr


@pytest.mark.parametrize("mode", ["basic", "tool", "structured"])
@pytest.mark.parametrize("proposed_inputs", [
    {},
    {
        "runtime_ready": True,
        "model": "different-model",
        "reviewed fit/fault-stop method": "proposed-method",
        "selected Granite operating envelope": {"selected": True, "limit": 1e308},
        "qualifying immutable C subject": {"accepted": True},
        "other": [None, False, 123, -0.5, "Tokyo"],
    },
])
def test_preparation_cli_retains_finite_proposals_without_resolving_requirements(mode, proposed_inputs):
    corpus = json.loads((TOOLS_DIR.parent / "inference/fixtures/granite-3.1-1b-a400m-instruct.json").read_text())
    expected = next(fixture["request"] for fixture in corpus["fixtures"] if fixture["mode"] == mode)

    result = _run_preparation_cli(
        "proposed-model", "--mode", mode, "--dry-run",
        "--proposed-inputs-json", json.dumps(proposed_inputs, allow_nan=False),
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "mode": mode,
        "status": "preparation-only",
        "runtime_ready": False,
        "model": {"value": "proposed-model", "status": "proposed/unverified"},
        "corpus": {
            "repo_id": "ibm-granite/granite-3.1-1b-a400m-instruct",
            "revision": "0da7a48b0276d500ce5922fd2b33944091fc6c09",
            "sha256": "cfc8740cdf71455fea91064caf3c8545763344c9b71803abf115323a6e98d094",
        },
        "request": expected,
        "unresolved_requirements": [
            "reviewed fit/fault-stop method",
            "selected Granite operating envelope",
            "qualifying immutable C subject",
        ],
        "proposed_inputs": {"values": proposed_inputs, "status": "proposed/unverified"},
    }


@pytest.mark.parametrize("proposed_inputs_json", [
    "", "{", '{"x":}', "null", "true", "42", '"literal"', "[{}]",
    '{"x":1,"x":2}',
    '{"nested":{"x":1,"x":2}}',
    '{"items":[{"x":1,"x":2}]}',
    '{"x":NaN}',
    '{"nested":{"x":Infinity}}',
    '{"items":[-Infinity]}',
    '{"x":1e400}',
    '{"nested":{"x":-1e400}}',
    '{"items":[1e400]}',
])
def test_preparation_cli_rejects_ambiguous_nonfinite_or_nonobject_proposals(proposed_inputs_json):
    result = _run_preparation_cli(
        "proposed-model", "--mode", "basic", "--dry-run",
        "--proposed-inputs-json", proposed_inputs_json,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "--proposed-inputs-json" in result.stderr
    assert "error: argument --proposed-inputs-json:" in result.stderr
