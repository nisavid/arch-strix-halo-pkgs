from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
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
    if isinstance(response, dict) and response.get("error") is not None:
        raise RuntimeError("Granite response must not contain an error")
    choices = response.get("choices") if isinstance(response, dict) else None
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise RuntimeError("Granite response requires exactly one choice")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise RuntimeError("Granite response requires an assistant message")
    if message.get("refusal") is not None:
        raise RuntimeError("Granite response must not contain a refusal")
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
    plain_log = re.sub(r"\x1b\[[0-9;]*m", "", server_log)
    selection = re.compile(
        r"(?:(?:\([A-Za-z_][\w.-]* pid=\d+\) )?"
        r"INFO(?: \d{2}-\d{2} \d{2}:\d{2}:\d{2})? "
        r"\[(?:[A-Za-z0-9_./-]+/)?unquantized\.py:\d+\] )?"
        r"Using ([A-Za-z0-9_-]+(?:[ \t]+[A-Za-z0-9_-]+)*) "
        r"Unquantized MoE backend out of potential backends: \[[^\]\r\n]*\]\."
    )
    names: set[str] = set()
    for line in plain_log.split("\n"):
        remaining = line.strip(" \t\r")
        line_names: set[str] = set()
        while remaining:
            match = selection.match(remaining)
            if match is None:
                break
            line_names.add(match.group(1))
            tail = remaining[match.end():]
            if tail and tail[0] not in " \t":
                break
            remaining = tail.lstrip(" \t")
        else:
            names.update(line_names)
    if not names:
        raise RuntimeError("Granite server log has no affirmative selected MoE backend")
    if len(names) != 1:
        raise RuntimeError(f"Granite server log has conflicting selected MoE backends: {sorted(names)}")
    return names.pop()


def _proposed_inputs_json(value: str) -> str:
    def finite_float(number: str) -> float:
        parsed = float(number)
        if not math.isfinite(parsed):
            raise ValueError("JSON numbers must be finite")
        return parsed

    try:
        parsed = json.loads(
            value,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=finite_float,
        )
    except (ValueError, RecursionError) as error:
        raise argparse.ArgumentTypeError(f"must be unambiguous finite JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("must contain a JSON object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a pinned Granite fixture request without executing it.")
    parser.add_argument("model", help="proposed model reference; not inspected or verified")
    parser.add_argument("--mode", choices=("basic", "tool", "structured"), required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--proposed-inputs-json",
        type=_proposed_inputs_json,
        help="unverified input proposals as one unambiguous finite JSON object",
    )
    args = parser.parse_args()
    if not args.dry_run:
        parser.error("Granite CPU preparation requires --dry-run; execution is not available")

    corpus_path = Path(__file__).resolve().parents[1] / "inference/fixtures/granite-3.1-1b-a400m-instruct.json"
    corpus_bytes = corpus_path.read_bytes()
    corpus = json.loads(corpus_bytes)
    fixture = next(fixture for fixture in corpus["fixtures"] if fixture["mode"] == args.mode)
    preparation = {
        "mode": args.mode,
        "status": "preparation-only",
        "runtime_ready": False,
        "model": {"value": args.model, "status": "proposed/unverified"},
        "corpus": {
            "repo_id": corpus["model_id"],
            "revision": corpus["revision"],
            "sha256": hashlib.sha256(corpus_bytes).hexdigest(),
        },
        "request": fixture["request"],
        "unresolved_requirements": [
            "reviewed fit/fault-stop method",
            "selected Granite operating envelope",
            "qualifying immutable C subject",
        ],
    }
    output = json.dumps(preparation)
    if args.proposed_inputs_json is not None:
        # The validated object remains JSON so decimal tokens are not rounded.
        output = (
            output[:-1]
            + ',"proposed_inputs":{"values":'
            + args.proposed_inputs_json
            + ',"status":"proposed/unverified"}}'
        )
    print(output)


if __name__ == "__main__":
    main()
