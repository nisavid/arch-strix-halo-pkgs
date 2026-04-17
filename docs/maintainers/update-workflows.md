# Update Workflows

This repository has four main update stories.

## 1. Upstream Source Update

Use when the packaged upstream project released a new version or commit you want
to adopt.

1. Read the package's `recipe.json` and `README.md`.
2. Confirm the authoritative base package and advisory references.
3. Scout upstream release notes, open issues, open PRs, and recent commits for
   fixes relevant to the lane you are touching, especially when validating a
   new model, feature, or usage pattern on a packaged stable release.
4. Update the package policy entry in `policies/recipe-packages.toml`.
5. Re-render the package scaffold.
6. Rebase or refresh patch files as needed.
7. Rebuild the package.
8. Refresh `repo/x86_64`.
9. Run package-specific smoke tests.
10. Update docs if the behavior, baseline, or maintenance story changed.

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
