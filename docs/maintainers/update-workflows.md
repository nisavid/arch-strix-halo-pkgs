# Update Workflows

This repository has four main update stories, plus a freshness sweep that
decides whether any of those stories must preempt ordinary backlog work.

## Package Versioning

Use the packaged upstream or source version as `pkgver`. Rendered
`recipe.json`, package READMEs, and TheRock manifests record the Blackcat
Informatics recipe commit, date, and path-history count as provenance.

Use `pkgrel` for local packaging changes, patch carry refreshes, rebuilds, and
recipe-input changes that do not change the packaged upstream/source version.
The local repo has a single operator, so a direct migration to this versioning
shape may use a one-time pacman downgrade.

## 0. Dependency Freshness Sweep

Run this daily sweep after closing a development arc and before starting a new
one only when the freshness state is due. Decide whether it is due before
running the checker. A matching checker cache entry or an acted-on completed
sweep from the previous 24 hours means the sweep is not due again. A tracked
completion note in `docs/maintainers/current-state.md` is enough evidence when
it records the completion time, outcome, and invalidating conditions. The
freshness policy lives in `policies/package-freshness.toml`; keep every
`packages/*/PKGBUILD` directory covered by exactly one freshness family.

Use the read-only checker instead of manually visiting release pages when the
gate is due or the recorded state is insufficient. For the ordinary daily
cadence, let the checker reuse a still-valid cache entry:

```sh
tools/check_package_updates.py --json --fail-on actionable
```

Force a new network sweep after changing package policy, package directories,
or freshness logic:

```sh
tools/check_package_updates.py --refresh --json --fail-on actionable
```

The checker writes only an ignored cache file under `.agents/session/`. It does
not upgrade packages, update submodules, edit policy, or modify docs.

With `--fail-on actionable`, the CLI exits `3` when a provider query failed
without a blocked disposition and exits `10` when the effective report still
has work requiring action, including missing dispositions and blocked
candidates. Tracked, rejected, and adopted candidates remain visible through
`effective_status` and `effective_summary`, but do not make the gate fail. A
zero exit means the report has no unhandled query failures or effective
action-required statuses, but still read the JSON summary before moving on.

Status handling:

- `current`: no upstream or baseline drift was found for that package family.
- `stable_update_available`: run the upstream source update story before
  unrelated backlog work.
- `branch_head_ahead`: review the VCS source lane and run the upstream source
  update story if the newer head belongs in this repo.
- `candidate_head_ahead`: review a branch lane that can become the next pinned
  package source snapshot, then either adopt a new pinned commit or record the
  reviewed head if the range does not belong in the package.
- `baseline_drift`: run the baseline package update story, then decide whether
  the drift should change local package policy.
- `scout_head_ahead`: review a branch lane used for fix discovery or patch
  reduction; this is advisory unless the review changes package policy or patch
  carry.
- `metadata_mismatch`: fix the freshness policy or package source metadata
  before trusting the sweep result.
- `query_failed`: the sweep is not clean; rerun or diagnose the failed provider
  check instead of treating the package as current.
- `prerelease_only`: record as informational unless the package family opts
  into prerelease adoption.
- `manual_review_required`: the family deliberately has no complete automated
  freshness check; inspect the documented lane before ordinary backlog work.

### Update Candidate Disposition

Freshness discovery and update disposition are separate facts. A newer upstream
version, branch head, baseline package, or canonical recipe input is not handled
merely because `policies/package-freshness.toml` records the latest value.

Every actionable freshness result must end in one of these durable dispositions:
adopted, tracked, rejected, or blocked. Active dispositions live in
`docs/maintainers/update-candidates.toml`; active follow-up work must also be
visible in `docs/backlog.md`.

Do not close a refresh by only updating `policies/package-freshness.toml`. Each
candidate must have a disposition in the update-candidate ledger before the
refresh is treated as handled.

Patch carry overlap is a reason to prioritize update review, not a reason to
defer an update. Absence of backend build-system changes is not enough to reject
a candidate; review runtime and user-facing platform relevance too.

`adopted` means the package source decision and the derived validation gates
are complete. If build, downstream rebuild, deploy/install, installed-smoke,
service-smoke, or live-scenario gates remain open, keep the candidate
`tracked` or `blocked` and point `next_gate_*` plus `docs/backlog.md` at that
work.

### Validation Gate Derivation

When package source refs, patches, build flags, dependency metadata, install
layout, generated outputs, service/config files, CLI/API behavior, or runtime
contracts change, derive the validation gates before PR or closeout.

Treat the affected set as the union of:

- directly changed package contracts
- declared build and runtime consumers from package metadata and
  `python tools/repo_package_graph.py --json <package-root> ...`
- documented or runtime couplings found in maintainer docs, package READMEs,
  tools, smoke tests, service definitions, config/env overlays, and tracked
  scenarios
- optional integrations that repo-owned docs, smokes, or scenarios actually
  exercise

Classify each affected contract into the strongest gate it needs:

- package tests or source checks for metadata-only changes
- package rebuild for changed source, patches, generated outputs, or build
  flags
- downstream rebuild when a consumer embeds, links, generates from, or
  build-imports the changed package
- deploy/install plus installed smoke when runtime imports, shared libraries,
  JIT/cache paths, entrypoints, services, or config overlays can change
- service smoke or live model/scenario run when user-facing service behavior,
  model behavior, dynamic backend/plugin selection, or documented scenario
  expectations can change

Record unresolved gates in `docs/maintainers/update-candidates.toml` and
`docs/backlog.md`. Final and PR summaries must distinguish source updated,
package built, deployed/installed, installed-smoked, and live-scenario
validated states.

The cache is valid only when the policy digest still matches and the cached
report is younger than `--max-age-hours` (24 by default). The digest includes
the checker version, freshness policy, update-candidate ledger, discovered
package directories, and any `--only` selectors.

Durable closeout notes may point future agents at the freshness gate, but the
instruction must preserve the gate's termination condition: stop before running
the checker when a valid cache entry or acted-on completed sweep keeps the
state fresh. If a completed sweep has already been triaged and any package
updates have been acted on, record the concrete completion time, outcome, and
invalidating conditions instead of implying that every new arc requires a
network rerun. The freshness state becomes due again after 24 hours or after
package policy, package directories, checker logic, or relevant source metadata
changes in a way that the completed sweep no longer covers.

Freshness `recorded` values are the last reviewed upstream or baseline values.
For branch checks, the recorded value may be newer than the packaged source
when the reviewed branch range did not justify changing the pinned package
commit.

If the sweep changes package policy, patch carry, validation status, or a known
blocker, update canonical docs under `docs/` and delete any session-only input
once its durable content has been extracted.

After rebuilding a dependency lane that can affect runtime behavior, treat
previous inference findings, expected-failure tests, backlog findings, and
local-origin runtime patch rationale as provisional until reproduced against
the installed rebuilt stack. Promote findings that reproduce after install,
retire findings that no longer reproduce, and make sure each retained
local-origin patch ends with a test or tracked scenario that guards the
behavior it fixes. Use `docs/maintainers/current-state.md`, `docs/patches.md`,
package READMEs, recipe metadata, scenario definitions, git history, and
available session transcripts to find the existing evidence and patch
motivation before inferring a retained-patch guard.

Current package-lane catalog:

| Lane | Packages | Scout first |
| --- | --- | --- |
| Tagged upstream tarball | `aocl-utils-gfx1151`, `python-gfx1151`, `python-vllm-rocm-gfx1151`, `python-torchvision-rocm-gfx1151` | upstream release notes, tag list, `source_url`, package README |
| PyPI source/wheel local closure | `python-numpy-gfx1151`, `python-sentencepiece-gfx1151`, `python-zstandard-gfx1151`, `python-asyncpg-gfx1151`, `python-openai-harmony-gfx1151`, `python-orjson-gfx1151`, `python-cryptography-gfx1151`, `python-torchao-rocm-gfx1151`, `python-mistral-common-gfx1151`, `python-transformers-gfx1151` | PyPI metadata, upstream changelog, Arch/AUR baseline |
| ROCm/framework source lane | `python-pytorch-opt-rocm-gfx1151`, `python-triton-gfx1151`, `python-aotriton-gfx1151`, `python-amd-aiter-gfx1151` | upstream branch/tag, candidate or scout branch refs, ROCm compatibility notes, package patches |
| Monorepo commit/release lane | `llama.cpp-hip-gfx1151`, `llama.cpp-vulkan-gfx1151`, `lemonade-server`, `lemonade-app` | upstream release/tag, recorded source revision, backend/runtime docs |
| CMake engine source lane | `stable-diffusion.cpp-vulkan-gfx1151` | pinned upstream commit, recursive submodules, AUR backend package, Blackcat recipe notes, package-local source patches, installed wrapper smoke |
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
   Treat candidate branch refs as possible pinned-source snapshots after review;
   treat scout branch refs as fix-discovery inputs unless the review changes
   the source lane decision.
4. Record the upstream release summary and a diff stat against the currently
   packaged source before editing. Pay special attention to files touched by
   local patch files, package-local tests, and smoke helpers.
5. Check whether upstream dependency metadata changed and reconcile it against
   the local pacman dependency closure.
6. Update the package policy entry in `policies/recipe-packages.toml`.
7. Re-render the package scaffold.
8. Apply the carried patch series to a clean new source tree. Refresh patches
   when they apply with fuzz or when nearby upstream context changed.
9. Derive the validation gates for the changed contracts and affected
   consumers.
10. Rebuild, deploy/install, and smoke test according to the derived gate set,
    then refresh `repo/x86_64` for package artifacts that are published
    locally.
11. Run package-specific tests plus every tracked smoke, service smoke,
    live-scenario, or blocked-probe lane required by the derived gates.
12. Update docs if the behavior, baseline, maintenance story, or validation
    status changed.

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

## 3. Blackcat Informatics Recipe Update

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

When a package needs ccache compiler wrappers, keep the wrapper directory local
to the package build tree and leave the cache store to the host ccache
configuration. Do not set `CCACHE_DIR` in PKGBUILDs or renderer templates.

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
