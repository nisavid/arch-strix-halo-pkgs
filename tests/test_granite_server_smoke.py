from __future__ import annotations

from pathlib import Path
import json
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
