---
name: rebuild-publish-install-local-packages
description: Use when rebuilding repo packages, republishing the local pacman repo, or reinstalling local package outputs on a host through the tracked repo workflow.
---

# Rebuild Publish Install Local Packages

Use `tools/amerge` as the canonical repo-side host workflow for merge planning,
rebuild, publish, install, resume, history, and logs.

## Default Use

- For a narrow package lane:

```bash
tools/amerge run python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151
```

- Also rebuild dependencies:

```bash
tools/amerge run --deps python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151
```

- Rebuild all repo roots or only installed repo outputs:

```bash
tools/amerge run --all
tools/amerge run --installed
```

- Resume a failed run:

```bash
tools/amerge resume latest
```

Use `tools/amerge history` and `tools/amerge logs latest --path` to inspect
retained state and logs.
Use `--preview=tree --color=always` when the user wants a colorized plan
captured in logs or chat; leave the default `--color=auto` for normal terminals.

## Operator Notes

- Hand the command to the user for privileged execution.
- The tool keeps one sudo session alive, uses sudo only for publish/install
  operations, and logs under `docs/worklog/amerge/<plan-id>/`. It also keeps
  sudo warm during build-only plans because `makepkg -s` may need sudo for
  missing build dependencies.
- With `run`, each package root is built, published, and installed before the
  next root, preserving dependency-order fast iteration. Selected split roots
  also install any outputs required by later selected package roots.
- If no targets or selectors are given, hand the command to the user only for an
  interactive session; noninteractive use should pass targets, `--all`, or
  `--installed`.
- For the common rebuild -> install -> test flow, follow with
  `python tools/run_inference_scenarios.py ...`.
- If shell glue is still needed around this Python CLI, use the `idiomatic-zsh`
  skill.
