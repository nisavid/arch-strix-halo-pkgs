# Local Repo Usage

The intended first-pass installation story is a local pacman repo on an Arch
system.

That keeps installs, repairs, and upgrades inside normal package-manager
behavior instead of long one-off `pacman -U` command lists.

## Build A Package

Build any package directory with normal `makepkg` usage:

```bash
(cd packages/<pkgname> && makepkg -f)
```

Do that for each package you want to publish into the local repo.

## Publish The Repo

The canonical package output inside the checkout is `repo/x86_64`. Pacman
should consume a world-traversable published copy, not a path buried inside a
private home directory.

Recommended published path:

- `/srv/pacman/strix-halo-gfx1151/x86_64`

Publish the current repo contents like this:

```bash
sudo install -d /srv/pacman/strix-halo-gfx1151
sudo rsync -a --delete repo/x86_64/ /srv/pacman/strix-halo-gfx1151/x86_64/
```

## Enable The Repo In Pacman

Create the repo stanza:

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

Refresh metadata:

```bash
sudo pacman -Sy
```

## Install The Stack

Use normal package-manager commands once the repo is enabled.

Example:

```bash
paru -S rocm-gfx1151 lemonade llama.cpp-hip-gfx1151 python-vllm-rocm-gfx1151
```

Prefer `paru` for everyday interactive use if that is already your habit. Drop
to raw `pacman` only when you need low-level repair or rehearsal behavior.

## Refresh The Repo After A Rebuild

After rebuilding a package, refresh the canonical repo metadata:

```bash
python tools/update_pacman_repo.py --package-dir packages/<pkgname> --repo-dir repo/x86_64
```

Then republish:

```bash
sudo rsync -a --delete repo/x86_64/ /srv/pacman/strix-halo-gfx1151/x86_64/
sudo pacman -Sy
```

## First Cutover

For an initial migration from an older monolithic replacement such as
`rocm-gfx1151-bin`:

1. publish the full replacement closure into the local repo
2. rehearse the transaction against a fake root
3. perform the live install from the local repo
4. run smoke tests immediately

That is the bring-up pattern used for the first successful cutover of this
stack.

## Repair Loop

For a narrow post-cutover fix:

```bash
python tools/update_pacman_repo.py --package-dir packages/<pkgname> --repo-dir repo/x86_64
sudo rsync -a --delete repo/x86_64/ /srv/pacman/strix-halo-gfx1151/x86_64/
sudo pacman -Sy
paru -S <pkgname>
```

Then rerun only the smoke tests that matter for the repaired package.

## Merge Packages With Amerge

Use `amerge` when you want one command to plan package work, rebuild selected
source packages, refresh `repo/x86_64`, republish the local pacman repo, and
reinstall through pacman.

```bash
tools/amerge run python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151
```

Other common entry points:

- rebuild every package root:

```bash
tools/amerge run --all
```

- rebuild outputs currently installed from this repo:

```bash
tools/amerge run --installed
```

- include dependencies in the rebuild:

```bash
tools/amerge run --deps python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151
```

- include reverse dependencies in the rebuild:

```bash
tools/amerge run --rdeps python-amd-aiter-gfx1151
```

By default, explicit targets rebuild only those targets. Dependencies are used
for ordering and can be opted into with `--deps`. If no targets or selectors are
given, `amerge` prompts on a TTY and fails fast otherwise. `run` executes each
root in merge order as build, publish, then install for that root's selected
outputs plus selected-root dependency outputs so later builds see earlier
rebuilt dependencies.

`amerge` also sanitizes user Python environment variables such as
`PYTHONPYCACHEPREFIX`, `PYTHONSTARTUP`, `PYTHONUSERBASE`, `PYTHON_EGG_CACHE`,
and `PYTHONPATH` before running plan commands, and records that in the step log
when any were present.

`amerge` has separate subcommands for phase-specific work:

```bash
tools/amerge build python-amd-aiter-gfx1151
tools/amerge publish python-amd-aiter-gfx1151
tools/amerge install python-amd-aiter-gfx1151
```

Interactive runs preview the merge plan and ask for confirmation unless
`-y/--noconfirm` is given. Noninteractive runs skip the prompt and preview
unless `--preview=flat` or `--preview=tree` is requested. Preview colors default
to `--color=auto`; use `--color=always` when capturing a colored preview and
`--color=never` for plain text.

Resume and inspect retained plans:

```bash
tools/amerge resume latest
tools/amerge resume latest --skip
tools/amerge history
tools/amerge logs latest --path
```

Logs go to:

- `docs/worklog/amerge/<plan-id>/plan.json`
- `docs/worklog/amerge/<plan-id>/state.json`
- `docs/worklog/amerge/<plan-id>/<run-id>.log`
- `docs/worklog/amerge/<plan-id>/logs/<step-id>/`

## Run Inference Scenarios

Use the Python harness to run tracked inference scenarios serially across
`vllm`, `llama.cpp`, and Lemonade.

Validated Gemma 4 26B A4B lane:

```bash
python tools/run_inference_scenarios.py \
  --scenario vllm.gemma4.26b-a4b.text.basic \
  --scenario vllm.gemma4.26b-a4b.server.basic \
  --model-path google/gemma-4-26B-A4B-it=/path/to/google/gemma-4-26B-A4B-it
```

The scenario catalog lives under `inference/scenarios/`.

You can also narrow by engine or model:

```bash
python tools/run_inference_scenarios.py --engine vllm
python tools/run_inference_scenarios.py --engine lemonade
```

If no selectors are given, the tool prompts on a TTY and fails fast otherwise.

The harness:

- writes a predictable run root under `docs/worklog/inference-runs/<timestamp>/`
- stores `run.json` plus per-scenario `plan.json`, `result.json`, `stdout.log`,
  `stderr.log`, and `server.log` when applicable
- resolves logical model ids to local filesystem paths through repeated
  `--model-path MODEL=PATH` bindings
- captures `amd-smi process -G --json` before and after `vllm` scenarios when
  `amd-smi` is available
- fails a `vllm` scenario early if a stale `VLLM::EngineCore` is already
  holding VRAM from an earlier run

Logs go to:

- `docs/worklog/inference-runs/<timestamp>/summary.json`
- `docs/worklog/inference-runs/<timestamp>/scenarios/<scenario-id>/`

`docs/worklog/` is intentionally ignored, so the full transcript can stay on
disk for iteration without polluting tracked docs.
