# Recipe Input Repo

The canonical recipe input for this packaging repo is the tracked
`upstream/ai-notes` git submodule.

That submodule is the repo-local copy of Blackcat Informatics' Strix Halo
recipe work. The render tools now prefer it automatically, so maintainers do
not need an external `/path/to/ai-notes` checkout just to re-render package
scaffolds or TheRock metadata.

## Default Behavior

- `python tools/render_recipe_scaffolds.py`
- `python tools/render_therock_pkgbase.py ...`
- `python tools/compute_recipe_version.py ...`

all resolve the recipe root in this order:

1. explicit `--recipe-root`
2. `STRIX_HALO_RECIPE_ROOT`
3. repo-local `upstream/ai-notes`

Use an override only when you are intentionally comparing against a different
recipe checkout.

## When To Update The Submodule

Update `upstream/ai-notes` when:

- a relevant `strix-halo/` recipe change should flow into this repo
- you want rendered `pkgver` data to reflect newer recipe history
- a package audit or scaffold diff needs to be compared against newer recipe
  inputs

Do not bump the submodule just because upstream moved. A submodule update is a
real input change to this repo and should be tied to an actual package,
workflow, or policy update.

## How To Update It

For a fresh checkout:

```bash
git submodule update --init --recursive
```

To inspect the current pinned recipe input:

```bash
git submodule status -- upstream/ai-notes
git -C upstream/ai-notes log --oneline --decorate -n 10 -- strix-halo
```

To adopt newer upstream recipe work:

```bash
git submodule update --remote --checkout upstream/ai-notes
git -C upstream/ai-notes log --oneline --decorate -n 10 -- strix-halo
```

Then:

1. re-render the affected package scaffolds
2. review the diff against current local policy and patch carry
3. rebuild the affected packages
4. refresh `repo/x86_64`
5. run the relevant host smokes

Example for recipe-managed packages:

```bash
python tools/render_recipe_scaffolds.py --only python-amd-aiter-gfx1151 --only python-vllm-rocm-gfx1151
```

Example for the TheRock pkgbase after staging a new `opt/rocm` tree:

```bash
python tools/render_therock_pkgbase.py --therock-root /
```

## Review Rule

Treat the submodule bump and the rendered package diff as one change story.
Do not update `upstream/ai-notes` without reviewing what changed in:

- `policies/recipe-packages.toml`
- generated `packages/*/PKGBUILD`
- generated `packages/*/recipe.json`
- generated `packages/*/README.md`

The submodule is an input, not an instruction to accept every upstream recipe
change verbatim.
