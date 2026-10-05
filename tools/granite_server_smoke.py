from __future__ import annotations

import json
import re
from typing import Any


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate field {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-JSON number {value}")


def _json_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, str):
        raise RuntimeError(f"Granite {label} must be a JSON string")
    try:
        parsed = json.loads(value, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except ValueError as error:
        raise RuntimeError(f"Granite {label} must be unambiguous JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Granite {label} must contain a JSON object")
    return parsed


def validate_granite_response(mode: str, response: Any) -> dict[str, Any]:
    """Validate one nonstreaming response against the selected Granite fixture."""
    if mode not in ("basic", "tool", "structured"):
        raise RuntimeError(f"Unknown Granite fixture mode: {mode!r}")
    choices = response.get("choices") if isinstance(response, dict) else None
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise RuntimeError("Granite response requires exactly one choice")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise RuntimeError("Granite response requires an assistant message")
    expected_finish = "tool_calls" if mode == "tool" else "stop"
    if choice.get("finish_reason") != expected_finish:
        raise RuntimeError(f"Granite {mode} response requires finish_reason {expected_finish}")
    if mode == "tool":
        if message.get("content") not in (None, ""):
            raise RuntimeError("Granite tool response must not contain unparsed text")
        calls = message.get("tool_calls")
        if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], dict):
            raise RuntimeError("Granite tool response requires exactly one parsed call")
        call = calls[0]
        if not isinstance(call.get("id"), str) or not call["id"].strip():
            raise RuntimeError("Granite tool call requires a nonempty id")
        function = call.get("function")
        if call.get("type") != "function" or not isinstance(function, dict) or function.get("name") != "get_weather":
            raise RuntimeError("Granite tool call must select get_weather")
        arguments = _json_object(function.get("arguments"), "tool arguments")
        if arguments != {"location": "Tokyo", "unit": "celsius"}:
            raise RuntimeError("Granite tool arguments must select Tokyo in celsius")
        return message
    if message.get("tool_calls") not in (None, []):
        raise RuntimeError(f"Granite {mode} response must not contain tool calls")
    content = message.get("content")
    if mode == "structured":
        if _json_object(content, "structured content") != {"topic": "ocean", "answer": "blue"}:
            raise RuntimeError("Granite structured response must contain only topic ocean and answer blue")
        return message
    if not isinstance(content, str) or content != "12":
        raise RuntimeError("Granite basic response must contain exactly 12")
    return message


def parse_selected_moe_backend(server_log: str) -> str:
    """Return the oracle's affirmative selection, not its candidate backend list."""
    if not isinstance(server_log, str):
        raise RuntimeError("Granite MoE evidence must be server-log text")
    names = {
        match.group(1).strip()
        for match in re.finditer(
            r"(?:^|\]\s*|(?<=\.)\s+)Using ([^\n]+?) Unquantized MoE backend out of potential backends: \[[^\]\n]*\]\.",
            server_log, re.MULTILINE,
        )
        if match.group(1).strip()
    }
    if not names:
        raise RuntimeError("Granite server log has no affirmative selected MoE backend")
    if len(names) != 1:
        raise RuntimeError(f"Granite server log has conflicting selected MoE backends: {sorted(names)}")
    return names.pop()
