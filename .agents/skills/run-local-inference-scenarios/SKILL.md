---
name: run-local-inference-scenarios
description: Use when validating repo-owned inference engines or model lanes through tracked TOML scenarios after package changes or host repairs.
---

# Run Local Inference Scenarios

Use `python tools/run_inference_scenarios.py` for repo-owned inference
validation. The harness is serial, scenario-driven, and logs to a predictable
run root.

## Default Use

- Run the validated Gemma 4 26B A4B lane:

```bash
python tools/run_inference_scenarios.py \
  --scenario vllm.gemma4.26b-a4b.text.basic \
  --scenario vllm.gemma4.26b-a4b.server.basic \
  --model-path google/gemma-4-26B-A4B-it=/absolute/path/to/google/gemma-4-26B-A4B-it
```

- Narrow by engine:

```bash
python tools/run_inference_scenarios.py --engine vllm
python tools/run_inference_scenarios.py --engine lemonade
```

If no selector args are given, the tool prompts on a TTY and fails fast
otherwise.

## Host Access

Run live vLLM, PyTorch HIP, ROCm, `rocminfo`, `amd-smi`, and server-smoke
scenarios outside the Codex bwrap sandbox. In Codex, request
`sandbox_permissions=require_escalated` for commands that need to open
`/dev/kfd` or `/dev/dri/renderD*`; adding those paths as writable roots is not
enough proof of usable device access.

The sandbox is fine for unit tests, catalog tests, adapter tests, and runner
dry-runs that do not initialize ROCm. Do not classify a live vLLM scenario as
GPU-unavailable until the command has been retried with host device access.

## Operator Notes

- Hand the command to the user when it exercises the live host.
- Logs land under `docs/worklog/inference-runs/<timestamp>/`.
- Each selected scenario gets `plan.json`, `result.json`, `stdout.log`,
  `stderr.log`, and `server.log` when applicable.
- vLLM scenarios also capture `amd-smi` process tables and fail early on a
  preexisting stale `VLLM::EngineCore`.
- For fresh package validation, run `tools/amerge run ...` first.
