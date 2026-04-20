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

- Deploy already-built package artifacts:

```bash
tools/amerge deploy python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151
```

Use `tools/amerge history` and `tools/amerge logs latest --path` to inspect
retained state and logs.
Use `--preview=tree --color=always` when the user wants a colorized plan
captured in logs or chat; leave the default `--color=auto` for normal terminals.
Use `--preview=commands` when the user wants to inspect exact `makepkg`,
publish, and pacman commands before privileged execution.

## Operator Notes

- Hand `run`, `publish`, `install`, and `deploy` commands to the user when
  they need privileged publish/install execution.
- When autonomous work produces package artifacts but cannot complete the
  privileged host mutation, close with the exact `tools/amerge deploy ...`
  command needed to publish and install those artifacts. Do not leave the user
  to infer the deployment step from build output or package drift notes.
- After the user reports the privileged command has completed, run the
  applicable `pacman -Q ...` and smoke checks yourself when the host is
  accessible. Ask the user to run verification only when you cannot perform it
  from the current environment.
- `tools/amerge build ...` is intentionally unprivileged and should be usable
  autonomously when package build dependencies are already installed. If
  `makepkg` needs missing dependencies, handle that as a host setup blocker
  rather than warming sudo up front.
- The tool keeps one sudo session alive only for plans containing privileged
  publish/install commands, and logs under `docs/worklog/amerge/<plan-id>/`.
- With `run`, each package root is built, published, and installed before the
  next root, preserving dependency-order fast iteration. Selected split roots
  also install any outputs required by later selected package roots.
- Publish steps require package archives matching the current PKGBUILD
  `makepkg --packagelist`, so stale built artifacts fail before republishing.
- A plan holds `active.lock` while running; do not start a second resume or run
  against the same plan if `history` reports it active.
- If no targets or selectors are given, hand the command to the user only for an
  interactive session; noninteractive use should pass targets, `--all`, or
  `--installed`.
- For the common rebuild -> install -> test flow, follow with
  `python tools/run_inference_scenarios.py ...`.
- If shell glue is still needed around this Python CLI, use the `idiomatic-zsh`
  skill.
