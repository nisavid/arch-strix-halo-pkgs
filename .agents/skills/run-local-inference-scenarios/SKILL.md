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

## Operator Notes

- Hand the command to the user when it exercises the live host.
- Logs land under `docs/worklog/inference-runs/<timestamp>/`.
- Each selected scenario gets `plan.json`, `result.json`, `stdout.log`,
  `stderr.log`, and `server.log` when applicable.
- vLLM scenarios also capture `amd-smi` process tables and fail early on a
  preexisting stale `VLLM::EngineCore`.
- For fresh package validation, run `tools/rebuild_publish_install.zsh` first.
