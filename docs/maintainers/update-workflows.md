# Update Workflows

This repository has four main update stories, plus a freshness sweep that
decides whether any of those stories must preempt ordinary backlog work.

## 0. Dependency Freshness Sweep

Run this sweep after closing a development arc and before starting a new one
when no sweep has been recorded in the previous 24 hours. Use ignored session
notes for a no-change sweep, and move only durable conclusions into tracked
docs.

1. List recipe-managed packages from `policies/recipe-packages.toml`.
2. For each package, check its package-specific upstream lane:
   - tagged release tarballs: upstream release page or tag list
   - PyPI sdists/wheels: PyPI release metadata
   - git tag or commit lanes: upstream tag list and recorded commit/ref
   - ROCm or framework branches: upstream branch head and release notes
   - recipe-derived inputs: `upstream/ai-notes` only when the recipe change is
     relevant to this repo
   - Arch/CachyOS/AUR baselines: the recorded authoritative reference first,
     then advisory references
3. If a newer upstream or baseline exists, classify it as one of the update
   stories below and run that story before unrelated backlog work.
4. If no relevant updates exist, record the sweep timestamp and package groups
   checked in an ignored session note such as
   `.agents/session/dependency-freshness-YYYYMMDDTHHMM.md`.
5. If the sweep changes package policy, patch carry, validation status, or a
   known blocker, update canonical docs under `docs/` and delete any
   session-only input once its durable content has been extracted.

Current package-lane catalog:

| Lane | Packages | Scout first |
| --- | --- | --- |
| Tagged upstream tarball | `aocl-utils-gfx1151`, `python-gfx1151`, `python-vllm-rocm-gfx1151`, `python-torchvision-rocm-gfx1151` | upstream release notes, tag list, `source_url`, package README |
| PyPI source/wheel with native build | `python-numpy-gfx1151`, `python-sentencepiece-gfx1151`, `python-zstandard-gfx1151`, `python-asyncpg-gfx1151`, `python-openai-harmony-gfx1151`, `python-orjson-gfx1151`, `python-cryptography-gfx1151`, `python-torchao-rocm-gfx1151` | PyPI metadata, upstream changelog, Arch/AUR baseline |
| ROCm/framework source lane | `python-pytorch-opt-rocm-gfx1151`, `python-triton-gfx1151`, `python-aotriton-gfx1151`, `python-amd-aiter-gfx1151` | upstream branch/tag, ROCm compatibility notes, package patches |
| Monorepo commit/release lane | `llama.cpp-hip-gfx1151`, `llama.cpp-vulkan-gfx1151`, `lemonade-server`, `lemonade-app` | upstream release/tag, recorded source revision, backend/runtime docs |
| Recipe-first or meta lane | `aocl-libm-gfx1151`, `lemonade` | Blackcat Informatics recipe input, local package closure, generated metadata |

Keep this table open-ended. When a new package class appears, add the lane
here at the same time as the package policy entry.

## 1. Upstream Source Update

Use when the packaged upstream project released a new version or commit you want
to adopt.

1. Read the package's `recipe.json` and `README.md`.
2. Confirm the authoritative base package and advisory references.
3. Scout upstream release notes, open issues, open PRs, and recent commits for
   fixes relevant to the lane you are touching, especially when validating a
   new model, feature, or usage pattern on a packaged stable release.
4. Record the upstream release summary and a diff stat against the currently
   packaged source before editing. Pay special attention to files touched by
   local patch files, package-local tests, and smoke helpers.
5. Check whether upstream dependency metadata changed and reconcile it against
   the local pacman dependency closure.
6. Update the package policy entry in `policies/recipe-packages.toml`.
7. Re-render the package scaffold.
8. Apply the carried patch series to a clean new source tree. Refresh patches
   when they apply with fuzz or when nearby upstream context changed.
9. Rebuild the package.
10. Refresh `repo/x86_64`.
11. Run package-specific tests plus every tracked smoke or blocked-probe lane
    that used to be part of the package's validated behavior.
12. Update docs if the behavior, baseline, or maintenance story changed.

Scout starting points:

- upstream release notes or tags
- the package's `authoritative_reference`
- sibling patch files
- package-local `update_notes`

## 2. Baseline Package Update

Use when Arch, CachyOS, or AUR changed the package that this repo uses as its
authoritative or advisory baseline.

1. Re-evaluate whether the currently recorded authoritative base is still the
   right one.
2. Update the recorded baseline metadata if that choice changed.
3. Review filesystem layout, dependency changes, split-package changes, and
   patch carry opportunities from the new baseline.
4. Fold in only the changes that actually improve this repo's maintained
   package story.
5. Re-render, rebuild, and smoke test.

Do not treat every baseline-package change as mandatory carry work. This repo
is allowed to diverge intentionally. The point is to keep those divergences
explicit.

## 3. Paudley Recipe Update

Use when `upstream/ai-notes/strix-halo` changed and the change should flow into this
package repo.

The repo-local `upstream/ai-notes` submodule is the canonical recipe input.
Read `docs/maintainers/recipe-inputs.md` before bumping it or overriding the
recipe root.

1. Identify which package families the recipe change affects.
2. Update the local `upstream/ai-notes` submodule if the repo should adopt the
   newer recipe input.
3. Re-render affected scaffolds from the updated recipe input.
4. Compare the rendered result against the current maintained PKGBUILD and
   patch set.
5. Keep the repo's local policy choices explicit; do not assume every recipe
   change should be adopted verbatim.
6. Rebuild, refresh the local repo, and smoke test.

If the recipe change only adds temporary bring-up knowledge, capture the stable
part in canonical docs and leave the transient part behind.

## 4. New Package From Recipe

Use when the recipe grows a new component that is not yet represented here.

1. Choose the same or closest compatibility lane for the base package.
2. Record:
   - authoritative base
   - advisory references
   - intentional divergences
   - update notes
3. Add the package policy entry.
4. Render the new scaffold.
5. Convert reusable source changes into patch files when practical.
6. Build, publish to the local repo, and test.

## 5. Choosing Local Package vs Dependency vs Optdepend

Use this when a repo-managed package starts referencing a Python or system
package that is not already part of the local-repo closure.

New local packages should default to this repo's applicable Strix optimization
lane: target the current Zen 5 / `znver5` host CPU (using explicit `znver5`
flags where a toolchain's plain `native` autodetection is unreliable), `-O3`
or the build system's equivalent, LTO when compatible, and PGO when the build
system exposes a maintainable training path. The decision about whether a
package belongs in this repo is separate from whether it should inherit that
default tuned build lane once it is here.

Prefer a normal dependency on an existing package when all of the following are
true:

1. the package is present in a supported repo lane the host can consume
   directly through pacman or the configured local repo workflow
2. the package is current enough for the upstream version lane in use here
3. the package metadata is complete enough to model the real runtime closure
4. this repo does not need compatibility patches, package-shape changes, or a
   different source lane
5. this repo does not need to carry the package locally just to keep the stack
   coherent, publishable, and reproducible through the documented pacman flow

Prefer a local package in this repo when any of the following are true:

1. the package is absent from official repos and the supported local-repo story
   would otherwise rely on pip or an AUR side-install for a hard runtime dep
2. the available baseline package is stale, incomplete, or otherwise wrong for
   this repo's update lane
3. the package needs compatibility patching for the Python, ROCm, or system
   library lane this repo maintains
4. the package needs a deliberate filesystem layout, dependency shape, or
   publish story that differs from the baseline package
Prefer an optdepend only when the feature is genuinely optional in this repo's
supported behavior:

1. upstream treats the feature as optional or extra-gated
2. imports are guarded so the base package remains import-clean and smoke-clean
3. this repo is comfortable treating the feature as unsupported until the
   optdepend is installed

For small helper libraries with native code, published manylinux wheels, and no
ROCm-specific compatibility delta, lack of an official Arch package is usually
still a closure problem rather than evidence that the package needs a special
ROCm lane. If this repo packages such a helper locally, it should still inherit
the repo's default applicable Strix tuning; the key question is whether the
package belongs in the local-repo closure at all, not whether it deserves a
"no optimization" exception.

## Required Outputs

For any of the above, the end state should leave behind:

- updated package metadata
- updated patch files if relevant
- a buildable package
- refreshed local repo contents
- updated canonical docs if the maintenance story changed

For system-affecting packages, "done" also implies the repo is publishable
through the local pacman repo flow documented in `docs/usage/local-repo.md`.
