# Update Workflows

This repository has four main update stories.

## 1. Upstream Source Update

Use when the packaged upstream project released a new version or commit you want
to adopt.

1. Read the package's `recipe.json` and `README.md`.
2. Confirm the authoritative base package and advisory references.
3. Update the package policy entry in `policies/recipe-packages.toml`.
4. Re-render the package scaffold.
5. Rebase or refresh patch files as needed.
6. Rebuild the package.
7. Refresh `repo/x86_64`.
8. Run package-specific smoke tests.
9. Update docs if the behavior, baseline, or maintenance story changed.

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

Use when `ai-notes/strix-halo` changed and the change should flow into this
package repo.

1. Identify which package families the recipe change affects.
2. Re-render affected scaffolds from the updated recipe input.
3. Compare the rendered result against the current maintained PKGBUILD and
   patch set.
4. Keep the repo's local policy choices explicit; do not assume every recipe
   change should be adopted verbatim.
5. Rebuild, refresh the local repo, and smoke test.

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

## Required Outputs

For any of the above, the end state should leave behind:

- updated package metadata
- updated patch files if relevant
- a buildable package
- refreshed local repo contents
- updated canonical docs if the maintenance story changed

For system-affecting packages, "done" also implies the repo is publishable
through the local pacman repo flow documented in `docs/usage/local-repo.md`.
