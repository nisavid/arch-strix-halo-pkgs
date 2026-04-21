from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


SERVER_MODES = (
    "reasoning",
    "reasoning-disabled",
    "mtp",
    "tool",
    "benchmark-lite",
    "advanced-selectors",
    "long-context-reduced",
    "media-embedding",
)
TEXT_ONLY_MODES = {
    "reasoning",
    "reasoning-disabled",
    "mtp",
    "tool",
    "benchmark-lite",
    "advanced-selectors",
    "long-context-reduced",
}
REASONING_MODES = {"reasoning", "reasoning-disabled", "mtp"}
BASIC_RESPONSE_MODES = {"benchmark-lite", "advanced-selectors", "long-context-reduced"}
TINY_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGNkSDjAwMDAxAAGAAzqASQOf3rKAAAAAElFTkSuQmCC"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Launch a local vLLM OpenAI-compatible server for a Qwen model and "
            "run a reduced recipe-aligned smoke."
        )
    )
    parser.add_argument("model", help="local model path or Hugging Face model id")
    parser.add_argument("--mode", choices=SERVER_MODES, default="reasoning")
    parser.add_argument(
        "--served-model-name",
        help="served model name exposed through /v1/models; defaults to the model argument",
    )
    parser.add_argument(
        "--draft-model",
        help="optional draft model path or Hugging Face id for draft-model speculative decoding",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.9)
    parser.add_argument(
        "--max-model-len",
        type=int,
        default=None,
        help="server max model length; defaults to the reduced local smoke value 1024",
    )
    parser.add_argument(
        "--max-num-batched-tokens",
        type=int,
        default=None,
        help=(
            "scheduler cap for model profiling and prefill batching; defaults "
            "to 32, except advanced-selectors defaults to 8192"
        ),
    )
    parser.add_argument(
        "--max-num-seqs",
        type=int,
        help="optional vLLM max sequence count; advanced-selectors defaults to 256",
    )
    parser.add_argument("--startup-timeout", type=float, default=420.0)
    parser.add_argument("--request-timeout", type=float, default=60.0)
    parser.add_argument(
        "--execution-mode",
        choices=("eager", "compiled"),
        default="eager",
        help="use eager correctness mode or allow vLLM compilation/cudagraph paths",
    )
    parser.add_argument(
        "--no-enforce-eager",
        dest="execution_mode",
        action="store_const",
        const="compiled",
        help="alias for --execution-mode compiled",
    )
    parser.add_argument(
        "--limit-mm-per-prompt",
        help=(
            "JSON limit map passed to vLLM; text modes default to "
            '{"audio":0,"image":0,"video":0}'
        ),
    )
    parser.add_argument(
        "--mm-processor-kwargs",
        help="JSON object forwarded as --mm-processor-kwargs",
    )
    parser.add_argument(
        "--server-log",
        type=Path,
        default=Path("/tmp/qwen-server-smoke.log"),
        help="log file for vLLM server stdout/stderr",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the derived server command and request payload as JSON without launching the server",
    )
    args = parser.parse_args()
    args.limit_mm_per_prompt_map = parse_json_object(
        args.limit_mm_per_prompt,
        option_name="--limit-mm-per-prompt",
    )
    args.mm_processor_kwargs_map = parse_json_object(
        args.mm_processor_kwargs,
        option_name="--mm-processor-kwargs",
    )
    args.server_log = args.server_log.resolve()
    return args


def parse_json_object(raw: str | None, *, option_name: str) -> dict[str, object] | None:
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{option_name} must be valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{option_name} must decode to a JSON object")
    return value


def served_model_name(args: argparse.Namespace) -> str:
    return args.served_model_name or args.model


def server_base_url(args: argparse.Namespace) -> str:
    return f"http://{args.host}:{args.port}"


def compact_json(value: dict[str, object]) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def effective_max_model_len(args: argparse.Namespace) -> int:
    if args.max_model_len is not None:
        return args.max_model_len
    return 1024


def effective_max_num_batched_tokens(args: argparse.Namespace) -> int:
    if args.max_num_batched_tokens is not None:
        return args.max_num_batched_tokens
    if args.mode == "advanced-selectors":
        return 8192
    return 32


def effective_max_num_seqs(args: argparse.Namespace) -> int | None:
    if args.max_num_seqs is not None:
        return args.max_num_seqs
    if args.mode == "advanced-selectors":
        return 256
    return None


def effective_limit_mm_per_prompt(args: argparse.Namespace) -> dict[str, object]:
    if args.limit_mm_per_prompt_map is not None:
        return args.limit_mm_per_prompt_map
    if args.mode in TEXT_ONLY_MODES:
        return {"audio": 0, "image": 0, "video": 0}
    if args.mode == "media-embedding":
        return {"audio": 0, "image": {"count": 1, "width": 2, "height": 2}, "video": 0}
    return {"audio": 0, "image": 1, "video": 0}


def effective_mm_processor_kwargs(args: argparse.Namespace) -> dict[str, object] | None:
    if args.mm_processor_kwargs_map is not None:
        return args.mm_processor_kwargs_map
    if args.mode == "media-embedding":
        return {
            "videos_kwargs": {
                "size": {
                    "longest_edge": 469762048,
                    "shortest_edge": 4096,
                },
            },
        }
    return None


def build_server_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        args.model,
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--served-model-name",
        served_model_name(args),
        "--trust-remote-code",
        "--tensor-parallel-size",
        "1",
        "--gpu-memory-utilization",
        str(args.gpu_memory_utilization),
        "--max-model-len",
        str(effective_max_model_len(args)),
        "--max-num-batched-tokens",
        str(effective_max_num_batched_tokens(args)),
        "--limit-mm-per-prompt",
        compact_json(effective_limit_mm_per_prompt(args)),
        "--disable-log-stats",
    ]
    if args.execution_mode == "eager":
        command.append("--enforce-eager")
    if args.mode in REASONING_MODES:
        command.extend(["--reasoning-parser", "qwen3"])
    if args.mode == "reasoning-disabled":
        command.extend(
            [
                "--default-chat-template-kwargs",
                compact_json({"enable_thinking": False}),
            ]
        )
    if args.draft_model:
        command.extend(
            [
                "--speculative-config",
                compact_json(
                    {
                        "method": "draft_model",
                        "model": args.draft_model,
                        "num_speculative_tokens": 2,
                    }
                ),
            ]
        )
    elif args.mode == "mtp":
        command.extend(
            [
                "--speculative-config",
                compact_json(
                    {
                        "method": "mtp",
                        "num_speculative_tokens": 2,
                    }
                ),
            ]
        )
    if args.mode == "tool":
        command.extend(["--enable-auto-tool-choice", "--tool-call-parser", "qwen3_coder"])
    if args.mode == "benchmark-lite":
        command.extend(["--no-enable-prefix-caching", "--async-scheduling"])
    max_num_seqs = effective_max_num_seqs(args)
    if max_num_seqs is not None:
        command.extend(["--max-num-seqs", str(max_num_seqs)])
    mm_processor_kwargs = effective_mm_processor_kwargs(args)
    if mm_processor_kwargs is not None:
        command.extend(["--mm-processor-kwargs", compact_json(mm_processor_kwargs)])
    return command


def build_tool_spec() -> list[dict[str, object]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather in a city.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name to look up.",
                        },
                        "unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "description": "Requested temperature unit.",
                        },
                    },
                    "required": ["location"],
                },
            },
        }
    ]


def request_max_tokens(args: argparse.Namespace, desired: int) -> int:
    reserve = 128 if args.mode in REASONING_MODES else 64
    budget = max(1, effective_max_model_len(args) - reserve)
    return max(1, min(desired, budget))


def build_request_payload(args: argparse.Namespace) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": served_model_name(args),
        "messages": [],
        "max_tokens": request_max_tokens(args, 32),
        "temperature": 0.0,
    }
    if args.mode == "reasoning":
        payload["messages"] = [
            {
                "role": "user",
                "content": (
                    "A snail climbs 3 feet each day and slips 2 feet each night "
                    "in a 20-foot well. How many days does it need to escape?"
                ),
            }
        ]
        payload["chat_template_kwargs"] = {"enable_thinking": True}
        payload["max_tokens"] = request_max_tokens(args, 256)
        payload["skip_special_tokens"] = False
        return payload
    if args.mode == "reasoning-disabled":
        payload["messages"] = [
            {"role": "user", "content": "Answer in one short sentence: what is 7 + 5?"}
        ]
        payload["chat_template_kwargs"] = {"enable_thinking": False}
        payload["skip_special_tokens"] = False
        return payload
    if args.mode == "mtp":
        payload["messages"] = [
            {"role": "user", "content": "Write one sentence about reliable testing."}
        ]
        payload["chat_template_kwargs"] = {"enable_thinking": True}
        payload["max_tokens"] = request_max_tokens(args, 128)
        payload["skip_special_tokens"] = False
        return payload
    if args.mode == "tool":
        payload["messages"] = [
            {"role": "user", "content": "What is the weather in Tokyo today? Use the tool."}
        ]
        payload["tools"] = build_tool_spec()
        payload["tool_choice"] = "auto"
        payload["max_tokens"] = request_max_tokens(args, 256)
        payload["skip_special_tokens"] = False
        return payload
    if args.mode == "benchmark-lite":
        payload["messages"] = [
            {"role": "user", "content": "Write exactly five words about inference."}
        ]
        payload["max_tokens"] = request_max_tokens(args, 8)
        return payload
    if args.mode == "advanced-selectors":
        payload["messages"] = [
            {"role": "user", "content": "Write a compact status sentence about batching."}
        ]
        return payload
    if args.mode == "long-context-reduced":
        payload["messages"] = [
            {
                "role": "user",
                "content": (
                    "Remember the needle word: quartz. "
                    "After this short reduced-context prompt, repeat only the needle word."
                ),
            }
        ]
        return payload
    if args.mode == "media-embedding":
        payload["messages"] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this tiny image in a few words."},
                    {"type": "image_url", "image_url": {"url": TINY_PNG_DATA_URL}},
                ],
            }
        ]
        return payload
    raise ValueError(f"unsupported mode: {args.mode}")


def build_tool_followup_payload(
    args: argparse.Namespace,
    assistant_message: dict[str, Any],
) -> dict[str, object]:
    tool_calls = assistant_message.get("tool_calls") or []
    if not tool_calls:
        raise RuntimeError("tool mode response did not include any tool_calls")
    tool_call = tool_calls[0]
    return {
        "model": served_model_name(args),
        "messages": [
            {"role": "user", "content": "What is the weather in Tokyo today? Use the tool."},
            assistant_message,
            {
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(
                    {
                        "temperature": 22,
                        "condition": "Partly cloudy",
                        "unit": "celsius",
                    },
                    sort_keys=True,
                ),
            },
        ],
        "tools": build_tool_spec(),
        "max_tokens": request_max_tokens(args, 256),
        "skip_special_tokens": False,
        "temperature": 0.0,
    }


def build_plan(args: argparse.Namespace) -> dict[str, object]:
    request_payload = build_request_payload(args)
    plan: dict[str, object] = {
        "mode": args.mode,
        "model": args.model,
        "draft_model": args.draft_model,
        "served_model_name": served_model_name(args),
        "execution_mode": args.execution_mode,
        "server_command": build_server_command(args),
        "startup_timeout": args.startup_timeout,
        "models_url": f"{server_base_url(args)}/v1/models",
        "request_url": f"{server_base_url(args)}/v1/chat/completions",
        "request_payload": request_payload,
        "server_log": str(args.server_log),
    }
    if args.mode == "tool":
        plan["followup_request_payload"] = build_tool_followup_payload(
            args,
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_qwen_weather",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"location":"Tokyo","unit":"celsius"}',
                        },
                    }
                ],
            },
        )
    return plan


def post_json(url: str, api_key: str, payload: dict[str, object], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url: str, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_server(
    process: subprocess.Popen[str],
    models_url: str,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited early with return code {process.returncode}")
        try:
            return get_json(models_url, timeout=5.0)
        except urllib.error.URLError:
            time.sleep(1.0)
    raise RuntimeError(f"timed out waiting for {models_url}")


def terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        pgid = os.getpgid(process.pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            return
        process.wait(timeout=10.0)


def extract_message(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError(f"response did not include any choices: {json.dumps(response, sort_keys=True)}")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError(f"response choice did not include a message: {json.dumps(response, sort_keys=True)}")
    return message


def validate_nonempty_text_response(response: dict[str, Any]) -> dict[str, Any]:
    message = extract_message(response)
    content = (message.get("content") or "").strip()
    if not content:
        raise RuntimeError("response did not include text content")
    if not re.search(r"[A-Za-z0-9]", content):
        raise RuntimeError(f"response did not include readable text: {content!r}")
    return message


def validate_reasoning_response(
    response: dict[str, Any],
    *,
    should_include_reasoning: bool,
) -> dict[str, Any]:
    message = extract_message(response)
    content = (message.get("content") or "").strip()
    reasoning = message.get("reasoning") or message.get("reasoning_content")
    if should_include_reasoning:
        if not content and not reasoning:
            raise RuntimeError("reasoning response had neither content nor reasoning output")
    elif reasoning:
        raise RuntimeError("reasoning-disabled response unexpectedly included reasoning output")
    elif not content:
        raise RuntimeError("reasoning-disabled response did not include text content")
    return message


def validate_tool_response(response: dict[str, Any]) -> dict[str, Any]:
    message = extract_message(response)
    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        raise RuntimeError("tool mode response did not include a tool call")
    function = tool_calls[0].get("function") or {}
    if function.get("name") != "get_weather":
        raise RuntimeError(f"unexpected tool call: {json.dumps(tool_calls[0], sort_keys=True)}")
    return message


def tail_log(path: Path, lines: int = 80) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(text[-lines:])


def run_smoke(args: argparse.Namespace) -> None:
    plan = build_plan(args)
    print("mode", args.mode)
    print("model", args.model)
    print("served_model_name", served_model_name(args))
    print("server_log", str(args.server_log))
    print("startup_timeout", plan["startup_timeout"])
    print("server_command", json.dumps(plan["server_command"]))

    args.server_log.parent.mkdir(parents=True, exist_ok=True)
    with args.server_log.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            plan["server_command"],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            models_payload = wait_for_server(
                process,
                str(plan["models_url"]),
                float(plan["startup_timeout"]),
            )
            print("server_ready")
            print("models_payload", json.dumps(models_payload, sort_keys=True))

            response = post_json(
                str(plan["request_url"]),
                args.api_key,
                dict(plan["request_payload"]),
                args.request_timeout,
            )
            print("initial_response", json.dumps(response, sort_keys=True))

            if args.mode == "reasoning":
                message = validate_reasoning_response(
                    response,
                    should_include_reasoning=True,
                )
                print("reasoning_field_present", bool(message.get("reasoning") or message.get("reasoning_content")))
                print("reasoning_ok")
            elif args.mode == "reasoning-disabled":
                message = validate_reasoning_response(
                    response,
                    should_include_reasoning=False,
                )
                print("reasoning_field_present", bool(message.get("reasoning") or message.get("reasoning_content")))
                print("reasoning_disabled_ok")
            elif args.mode == "mtp":
                validate_reasoning_response(response, should_include_reasoning=True)
                print("mtp_ok")
            elif args.mode == "tool":
                assistant_message = validate_tool_response(response)
                followup_payload = build_tool_followup_payload(args, assistant_message)
                followup = post_json(
                    str(plan["request_url"]),
                    args.api_key,
                    followup_payload,
                    args.request_timeout,
                )
                print("followup_response", json.dumps(followup, sort_keys=True))
                validate_nonempty_text_response(followup)
                print("tool_ok")
            elif args.mode in BASIC_RESPONSE_MODES:
                validate_nonempty_text_response(response)
                print(args.mode.replace("-", "_") + "_ok")
            elif args.mode == "media-embedding":
                validate_nonempty_text_response(response)
                print("media_embedding_ok")
            else:
                raise ValueError(f"unsupported mode: {args.mode}")
        except Exception:
            print("server_log_tail_start", file=sys.stderr)
            tail = tail_log(args.server_log)
            if tail:
                print(tail, file=sys.stderr)
            print("server_log_tail_end", file=sys.stderr)
            raise
        finally:
            terminate_process(process)


def main() -> None:
    args = parse_args()
    plan = build_plan(args)
    if args.dry_run:
        json.dump(plan, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return
    run_smoke(args)


if __name__ == "__main__":
    main()
