---
name: rebuild-publish-install-local-packages
description: Use when rebuilding repo packages, republishing the local pacman repo, or reinstalling local package outputs on a host through the tracked repo workflow.
---

# Rebuild Publish Install Local Packages

Use `tools/rebuild_publish_install.zsh` as the canonical repo-side host
workflow for rebuild, publish, and reinstall.

## Default Use

- For a narrow package lane:

```bash
tools/rebuild_publish_install.zsh python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151
```

- For repo packages already installed on the host:

```bash
tools/rebuild_publish_install.zsh --install-scope installed
```

- For the full repo package set:

```bash
tools/rebuild_publish_install.zsh --install-scope all
```

If no package args and no `--install-scope` are given, the tool prompts on a
TTY and fails fast otherwise.

## Operator Notes

- Hand the command to the user for privileged execution.
- The tool keeps one sudo session alive, uses sudo only for publish/install
  operations, and logs under `docs/worklog/rebuild-install-runs/<timestamp>/`.
- For the common rebuild -> install -> test flow, follow with
  `python tools/run_inference_scenarios.py ...`.
- If you need to write or edit repo shell tooling while working here, use the
  `idiomatic-zsh` skill.
