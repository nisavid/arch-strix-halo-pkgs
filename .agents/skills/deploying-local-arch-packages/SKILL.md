---
name: deploying-local-arch-packages
description: Use when Arch package changes need a host handoff, rebuild, publish, install, deploy, reinstall, downgrade, local pacman repo refresh, or post-change package verification in this repo.
---

# Deploying Local Arch Packages

Use `tools/amerge` as the canonical repo-side host workflow for merge planning,
rebuild, publish, install, resume, history, and logs.

## Completion Rule

When package files, PKGBUILDs, repo metadata, or package versions changed and
the privileged host mutation was not run, the final response must include the
exact `tools/amerge ...` handoff command.

Default handoff after broad package changes:

```bash
tools/amerge run --installed
```

If package artifacts are already built and only publish/install remains:

```bash
tools/amerge deploy <package-root>...
```

If the user wants to inspect the privileged commands first:

```bash
tools/amerge run --installed --preview=commands
```

## Command Selection

- Narrow package lane:

```bash
tools/amerge run python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151
```

- Include dependencies:

```bash
tools/amerge run --deps python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151
```

- Rebuild all repo roots:

```bash
tools/amerge run --all
```

- Resume a failed run:

```bash
tools/amerge resume latest
```

- Deploy already-built package artifacts:

```bash
tools/amerge deploy python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151
```

Inspect retained state with `tools/amerge history` and
`tools/amerge logs latest --path`. Use `--preview=tree --color=always` when the
user wants a colorized plan captured in logs or chat.

## Operator Notes

- Hand `run`, `publish`, `install`, and `deploy` commands to the user when
  privileged publish/install execution is needed and you have not run it.
- When artifacts are built but host mutation is pending, close with the exact
  `tools/amerge deploy ...` command. Do not leave the deployment step implicit.
- After the user reports the privileged command has completed, run the
  applicable `pacman -Q ...` and smoke checks yourself when the host is
  accessible. Ask the user to run verification only when you cannot perform it
  from the current environment.
- `tools/amerge build ...` is intentionally unprivileged and should be usable
  autonomously when package build dependencies are already installed. If
  `makepkg` needs missing dependencies, handle that as a host setup blocker
  rather than warming sudo up front.
- The tool validates sudo once for plans containing privileged steps, keeps the
  sudo validation timestamp fresh, runs privileged commands with
  noninteractive sudo, and logs under `docs/worklog/amerge/<plan-id>/`.
- With `run`, each package root is built and published immediately. Rebuilt
  repo outputs are installed in prerequisite transactions when the next build
  group needs them via `depends` or `makedepends`, and remaining selected
  outputs are installed in a final transaction.
- Publish steps require package archives matching the current PKGBUILD
  `makepkg --packagelist`, so stale built artifacts fail before republishing.
- A `--require-packagelist` publish treats current PKGBUILD outputs as
  authoritative for their package names and preserves unrelated repo packages.
- A plan holds `active.lock` while running; do not start a second resume or run
  against the same plan if `history` reports it active.
- If no targets or selectors are given, hand the command to the user only for an
  interactive session; noninteractive use should pass targets, `--all`, or
  `--installed`.
- For the common rebuild -> install -> test flow, follow with
  `python tools/run_inference_scenarios.py ...`.
- If shell glue is still needed around this Python CLI, use the `idiomatic-zsh`
  skill.
