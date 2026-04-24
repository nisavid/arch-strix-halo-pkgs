# Local Repo Usage

This repo is meant to produce a local pacman repository for a Strix Halo Arch
host. The local repo keeps installs, upgrades, downgrades, repairs, and smoke
validation inside the package manager instead of spreading state across manual
`pacman -U` commands and build directories.

`repo/x86_64` is the working package repo inside this checkout. It is ignored
by Git and can be missing or stale. Treat it as a build output, not as source of
truth.

## The Short Version

If package archives are already present in `repo/x86_64`, publish them:

```bash
sudo install -d /srv/pacman/strix-halo-gfx1151/x86_64
sudo rsync -a --delete repo/x86_64/ /srv/pacman/strix-halo-gfx1151/x86_64/
```

After completing [Enable The Repo In Pacman](#enable-the-repo-in-pacman) below once, refresh metadata and install packages:

```bash
sudo pacman -Sy
paru -S rocm-gfx1151 python-vllm-rocm-gfx1151 llama.cpp-hip-gfx1151 lemonade
```

If the repo has not been built yet, build packages first with `makepkg` or
`tools/amerge`, then publish the resulting `repo/x86_64` directory. The exact
pacman stanza is below.

## Build One Package

Use normal `makepkg` workflow inside a package directory:

```bash
(cd packages/<pkgname> && makepkg -f)
```

After a build, refresh the working package repo from that package directory:

```bash
python tools/update_pacman_repo.py \
  --package-dir packages/<pkgname> \
  --repo-dir repo/x86_64 \
  --require-packagelist
```

The updater treats the current PKGBUILD's package archives as authoritative for
that package's output names while preserving unrelated packages already present
in `repo/x86_64`.

## Publish The Local Repo

Pacman should consume a world-traversable published copy, not a checkout path in
a private home directory.

Recommended published path:

```text
/srv/pacman/strix-halo-gfx1151/x86_64
```

Publish the current working repo contents:

```bash
sudo install -d /srv/pacman/strix-halo-gfx1151/x86_64
sudo rsync -a --delete repo/x86_64/ /srv/pacman/strix-halo-gfx1151/x86_64/
```

## Enable The Repo In Pacman

Create a pacman include file:

```bash
printf '%s\n' \
  '[strix-halo-gfx1151]' \
  'SigLevel = Optional TrustAll' \
  'Server = file:///srv/pacman/strix-halo-gfx1151/x86_64' \
  | sudo tee /etc/pacman.d/strix-halo-gfx1151.conf >/dev/null
```

Include it from `/etc/pacman.conf` if it is not already included:

```bash
grep -qxF 'Include = /etc/pacman.d/strix-halo-gfx1151.conf' /etc/pacman.conf \
  || echo 'Include = /etc/pacman.d/strix-halo-gfx1151.conf' \
  | sudo tee -a /etc/pacman.conf >/dev/null
```

Refresh package metadata:

```bash
sudo pacman -Sy
```

## Install Packages

Use ordinary package-manager commands once the repo is enabled.

Typical local-inference stack:

```bash
paru -S rocm-gfx1151 python-vllm-rocm-gfx1151 llama.cpp-hip-gfx1151 lemonade
```

Use `paru` for everyday interactive use if that is already your normal Arch
workflow. Drop to raw `pacman` when you need lower-level repair, rehearsal, or
transaction debugging.

## Refresh After A Rebuild

For a narrow post-build refresh and reinstall:

```bash
python tools/update_pacman_repo.py \
  --package-dir packages/<pkgname> \
  --repo-dir repo/x86_64 \
  --require-packagelist
sudo rsync -a --delete repo/x86_64/ /srv/pacman/strix-halo-gfx1151/x86_64/
sudo pacman -Sy
paru -S <pkgname>
```

Then rerun the smallest smoke test that proves the repaired package behavior.

## First Cutover From Another ROCm Stack

For an initial migration from a monolithic replacement package such as
`rocm-gfx1151-bin`:

1. Publish the full replacement closure into the local repo.
2. Rehearse the pacman transaction against a fake root when the package closure
   or conflict set is uncertain.
3. Perform the live install from the local repo.
4. Run smoke tests immediately and record durable outcomes in the maintainer
   docs when the result changes the repo's known state.

This is the pattern used for the first successful live cutover of this stack.

## Use Amerge For Package Workflows

`amerge` plans package work, rebuilds selected source packages, refreshes
`repo/x86_64`, republishes the local pacman repo, and reinstalls through
pacman.

Build, publish, and install selected packages:

```bash
tools/amerge run python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151
```

Other common selectors:

```bash
tools/amerge run --all
tools/amerge run --installed
tools/amerge run --deps python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151
tools/amerge run --rdeps python-amd-aiter-gfx1151
```

By default, explicit targets rebuild only those targets. Dependencies are used
for ordering and can be opted into with `--deps`. If no targets or selectors
are given, `amerge` prompts on a TTY and fails fast otherwise.

`run` builds roots in merge order and publishes each root immediately after a
successful build. When later selected builds need rebuilt repo outputs through
`depends` or `makedepends`, `amerge` installs the needed outputs in one
prerequisite transaction. Any remaining selected outputs are installed together
at the end.

`amerge` also sanitizes user Python environment variables such as
`PYTHONPYCACHEPREFIX`, `PYTHONSTARTUP`, `PYTHONUSERBASE`, `PYTHON_EGG_CACHE`,
and `PYTHONPATH` before running plan commands, and records that cleanup in the
step log when any were present.

### Phase-Specific Amerge Commands

```bash
tools/amerge build python-amd-aiter-gfx1151
tools/amerge publish python-amd-aiter-gfx1151
tools/amerge install python-amd-aiter-gfx1151
tools/amerge deploy python-amd-aiter-gfx1151
```

- `build` runs package builds only and does not pre-warm sudo. Use it for
  unprivileged rebuild attempts when host build dependencies are already
  installed.
- `publish` refreshes the working repo and published pacman repo for selected
  package outputs.
- `install` installs selected outputs through pacman.
- `deploy` skips `makepkg`; use it after packages already exist and only the
  host-facing publish/install half remains.

`run`, `publish`, and `install` validate sudo once before step execution, keep
the sudo timestamp fresh during the plan, and execute privileged commands with
noninteractive sudo so mid-run commands fail instead of prompting.

Noninteractive install steps pass pacman's conflict-removal answer bit so
packages that intentionally conflict with an installed baseline can replace it
in the same transaction. Package metadata must still declare `conflicts` and,
for renamed or superseded packages, `replaces`.

### Preview, Resume, And Inspect Amerge Plans

Interactive runs preview the merge plan and ask for confirmation unless
`-y/--noconfirm` is given. Noninteractive runs skip the prompt and preview
unless `--preview=flat`, `--preview=tree`, or `--preview=commands` is requested.
Use the commands preview when you want to inspect the exact `makepkg`, publish,
and install commands before privileged operations.

```bash
tools/amerge run --preview=tree python-vllm-rocm-gfx1151
tools/amerge run --preview=commands python-vllm-rocm-gfx1151
```

Preview colors default to `--color=auto`; use `--color=always` when capturing a
colored preview and `--color=never` for plain text.

Resume and inspect retained plans:

```bash
tools/amerge resume latest
tools/amerge resume latest --skip
tools/amerge history
tools/amerge history show <short-id>
tools/amerge logs latest --path
```

`amerge history` is an alias for `amerge history list`. It renders retained
plans as a compact table with the short hex ID, local creation time, status,
command, and an elided target list. Use `amerge history show <short-id>` for
the full target list, run IDs, step status, and retained plan path. The short
hex ID is the suffix of `<plan-id>` and can also be used with `amerge resume`
and `amerge logs` when it uniquely identifies a retained plan.

Retained plan files live under `docs/worklog/amerge/<plan-id>/`:

- `plan.json`
- `state.json`
- `<run-id>.log`
- `logs/<step-id>/`
- `active.lock` for the active plan lock

State files are written through atomic replacement so interrupted runs remain
inspectable and resumable. Retained JSON timestamps are persisted in UTC and
rendered in local time for human history output.

## Run Inference Scenarios

Use the Python harness to run tracked inference scenarios serially across
`vllm`, `llama.cpp`, Lemonade, FlashAttention, Torch-MIGraphX, and other local
lanes represented in the catalog.

Run a known Gemma 4 lane with explicit model binding:

```bash
python tools/run_inference_scenarios.py \
  --scenario vllm.gemma4.26b-a4b.text.basic \
  --scenario vllm.gemma4.26b-a4b.server.basic \
  --model-path google/gemma-4-26B-A4B-it=/path/to/google/gemma-4-26B-A4B-it
```

Run package-entrypoint smokes for the current `llama.cpp` and Lemonade lanes:

```bash
python tools/run_inference_scenarios.py --engine llama.cpp --engine lemonade --tag smoke
```

Narrow by engine:

```bash
python tools/run_inference_scenarios.py --engine vllm
python tools/run_inference_scenarios.py --engine lemonade
```

If no selectors are given, the tool prompts on a TTY and fails fast otherwise.

The scenario catalog lives under `inference/scenarios/`. The harness writes run
records under `docs/worklog/inference-runs/<timestamp>/`, including summary
JSON plus per-scenario plans, results, logs, and server logs when applicable.
`docs/worklog/` is intentionally ignored, so full transcripts can stay on disk
for iteration without polluting tracked docs.

The harness resolves logical model IDs to local filesystem paths through
repeated `--model-path MODEL=PATH` bindings. Keep tracked docs on model IDs and
runtime bindings rather than committed cache snapshot paths.
