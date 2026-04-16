from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VENDORED_TOOL_CHAT_TEMPLATE = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/examples/tool_chat_template_gemma4.jinja"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Launch a local vLLM OpenAI-compatible server for a Gemma 4 -it model "
            "and run a basic, reasoning, or tool-calling smoke."
        )
    )
    parser.add_argument(
        "model",
        help="local model path or Hugging Face model id to serve",
    )
    parser.add_argument(
        "--mode",
        choices=("basic", "reasoning", "tool"),
        default="basic",
        help="which OpenAI-compatible server flow to validate",
    )
    parser.add_argument(
        "--served-model-name",
        help="served model name exposed through /v1/models; defaults to the model argument",
    )
    parser.add_argument(
        "--chat-template",
        type=Path,
        help=(
            "Gemma 4 tool chat template path; defaults to the vendored upstream "
            "template for --mode=tool"
        ),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.75)
    parser.add_argument(
        "--max-model-len",
        type=int,
        default=None,
        help=(
            "server max model length; defaults to 512 for basic mode and 1024 "
            "for reasoning/tool modes"
        ),
    )
    parser.add_argument("--startup-timeout", type=float, default=180.0)
    parser.add_argument("--request-timeout", type=float, default=60.0)
    parser.add_argument(
        "--server-log",
        type=Path,
        default=Path("/tmp/gemma4-server-smoke.log"),
        help="log file for vLLM server stdout/stderr",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the derived server command and request payload as JSON without launching the server",
    )
    args = parser.parse_args()

    if args.mode == "tool" and args.chat_template is None:
        args.chat_template = VENDORED_TOOL_CHAT_TEMPLATE
    if args.chat_template is not None:
        args.chat_template = args.chat_template.resolve()
    if args.mode == "tool" and not args.chat_template.is_file():
        parser.error(f"Gemma 4 tool chat template not found: {args.chat_template}")
    args.server_log = args.server_log.resolve()
    return args


def served_model_name(args: argparse.Namespace) -> str:
    return args.served_model_name or args.model


def server_base_url(args: argparse.Namespace) -> str:
    return f"http://{args.host}:{args.port}"


def effective_max_model_len(args: argparse.Namespace) -> int:
    if args.max_model_len is not None:
        return args.max_model_len
    if args.mode in {"reasoning", "tool"}:
        return 1024
    return 512


def build_server_command(args: argparse.Namespace) -> list[str]:
    limit_mm_per_prompt = json.dumps({"image": 0, "audio": 0}, separators=(",", ":"))
    max_model_len = effective_max_model_len(args)
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
        str(max_model_len),
        "--enforce-eager",
        "--limit-mm-per-prompt",
        limit_mm_per_prompt,
        "--disable-log-stats",
    ]
    if args.mode == "reasoning":
        command.extend(["--reasoning-parser", "gemma4"])
    if args.mode == "tool":
        command.extend(
            [
                "--reasoning-parser",
                "gemma4",
                "--tool-call-parser",
                "gemma4",
                "--enable-auto-tool-choice",
                "--chat-template",
                str(args.chat_template),
            ]
        )
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
    budget = max(1, effective_max_model_len(args) - 128)
    return max(1, min(desired, budget))


def build_request_payload(args: argparse.Namespace) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": served_model_name(args),
        "messages": [],
        "max_tokens": request_max_tokens(args, 64),
        "temperature": 0.0,
    }
    if args.mode == "basic":
        payload["messages"] = [
            {"role": "user", "content": "Write exactly five words about the ocean."}
        ]
        return payload
    if args.mode == "reasoning":
        payload["messages"] = [
            {
                "role": "user",
                "content": (
                    "A snail is at the bottom of a 20-foot well. "
                    "Each day it climbs 3 feet and each night it slides back 2 feet. "
                    "How many days does it take to reach the top?"
                ),
            }
        ]
        payload["chat_template_kwargs"] = {"enable_thinking": True}
        payload["max_tokens"] = request_max_tokens(args, 1024)
        payload["skip_special_tokens"] = False
        return payload

    payload["messages"] = [
        {"role": "user", "content": "What is the weather in Tokyo today? Use the tool."}
    ]
    payload["tools"] = build_tool_spec()
    payload["tool_choice"] = "auto"
    payload["max_tokens"] = request_max_tokens(args, 512)
    payload["skip_special_tokens"] = False
    return payload


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
        "max_tokens": request_max_tokens(args, 512),
        "skip_special_tokens": False,
        "temperature": 0.0,
    }


def build_plan(args: argparse.Namespace) -> dict[str, object]:
    request_payload = build_request_payload(args)
    plan: dict[str, object] = {
        "mode": args.mode,
        "model": args.model,
        "served_model_name": served_model_name(args),
        "server_command": build_server_command(args),
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
                        "id": "call_gemma4_weather",
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
    process.terminate()
    try:
        process.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10.0)


def extract_message(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError(f"response did not include any choices: {json.dumps(response, sort_keys=True)}")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError(f"response choice did not include a message: {json.dumps(response, sort_keys=True)}")
    return message


def validate_basic_response(response: dict[str, Any]) -> dict[str, Any]:
    message = extract_message(response)
    content = (message.get("content") or "").strip()
    if not content:
        raise RuntimeError("basic mode response content was empty")
    return message


def validate_reasoning_response(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError(f"response did not include any choices: {json.dumps(response, sort_keys=True)}")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeError(f"response choice did not include a message: {json.dumps(response, sort_keys=True)}")
    content = (message.get("content") or "").strip()
    reasoning = message.get("reasoning") or message.get("reasoning_content")
    finish_reason = choice.get("finish_reason")
    if finish_reason == "length" and not reasoning and content.startswith("thought"):
        raise RuntimeError(
            "reasoning response truncated inside the Gemma 4 thought block; "
            "increase --max-model-len and rerun"
        )
    if not content and not reasoning:
        raise RuntimeError("reasoning mode response had neither content nor reasoning output")
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
    print("server_command", json.dumps(plan["server_command"]))

    args.server_log.parent.mkdir(parents=True, exist_ok=True)
    with args.server_log.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            plan["server_command"],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            models_payload = wait_for_server(
                process,
                str(plan["models_url"]),
                args.startup_timeout,
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

            if args.mode == "basic":
                validate_basic_response(response)
                print("basic_ok")
            elif args.mode == "reasoning":
                message = validate_reasoning_response(response)
                print("reasoning_field_present", bool(message.get("reasoning") or message.get("reasoning_content")))
                print("reasoning_ok")
            else:
                assistant_message = validate_tool_response(response)
                followup_payload = build_tool_followup_payload(args, assistant_message)
                followup = post_json(
                    str(plan["request_url"]),
                    args.api_key,
                    followup_payload,
                    args.request_timeout,
                )
                print("followup_response", json.dumps(followup, sort_keys=True))
                validate_basic_response(followup)
                print("tool_ok")
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
