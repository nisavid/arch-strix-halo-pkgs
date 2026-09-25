# TheRock Split Generator

## Purpose

`generators/therock_split.py` scaffolds the local Arch split-package ROCm
family from a staged TheRock install tree.

`tools/render_therock_pkgbase.py` is the normal operator entrypoint. It wraps
the generator, takes `pkgver` from `policies/therock-packages.toml`, stamps
recipe attribution/provenance, and renders the package base into
`packages/therock-gfx1151/`.

The design goal is:

1. automate ownership assignment for known component classes
2. keep package metadata in a policy file rather than hardcoding it in the
   generator
3. fail with explicit machine-readable diagnostics for new or ambiguous
   components

The generator is intentionally strict. A loud structural failure is better than
silently assigning new TheRock content to the wrong package.

## Inputs

- `--root`: filesystem root containing the staged install tree, default `/`
- `--policy`: policy file, default `policies/therock-packages.toml`
- `--output`: generated output directory
- `--pkgver-override`: rendered package version override, normally supplied
  from policy by `tools/render_therock_pkgbase.py`
- recipe attribution flags used by `render_therock_pkgbase.py`
- `--skip-missing-soname-depends`: warn instead of failing when a
  `soname_depends` ELF is not staged yet. `render_therock_pkgbase.py` passes it
  for `--pre-migraphx-dry-render`, which refuses output under `packages/`

The policy currently assumes the actual TheRock payload lives under
`opt/rocm/`.

Package-added integration overlays that also live under `opt/rocm/` are not
part of the upstream TheRock payload and must be represented either as
synthetic files or post-copy commands plus matching ignore rules. Otherwise a
rerender against a live installed root will try to classify this repo's own
overlay files as new upstream content.

## Output authority

The rendered `packages/therock-gfx1151/` tree is authoritative for the staged
root used by the render. Each run rewrites the split `PKGBUILD`, manifest, and
current per-package file lists, and removes per-package file lists for packages
whose payload is no longer present in that staged root.

Package metadata may exist for upstream TheRock projects that are not present
in a particular staged root. Those packages stay recorded in the manifest as
not rendered, but the generator does not keep empty package functions or stale
file lists for them. To package more upstream projects, build or stage a
TheRock root that actually contains their installed payloads, then rerender.

Package `provides`, `conflicts`, `replaces`, and `depends` metadata comes from
`policies/therock-packages.toml`. Use those policy fields to model distro
package compatibility, replacement of old package names, and local split-package
runtime edges instead of editing generated `PKGBUILD` functions.

A package's `soname_depends` entries render pacman soname depends from staged
ELF files. Each entry names a staged library and a library stem, for example
`{ library = "opt/rocm/lib/migraphx/lib/libmigraphx_onnx.so", needed =
"libprotobuf.so" }`. The generator reads that library's `DT_NEEDED`, finds the
single `libprotobuf.so.<ver>` entry, and appends `libprotobuf.so=<ver>-64` to
the package's depends in the `PKGBUILD` and manifest. A rebuild against a
different protobuf therefore moves the depend without a policy edit.

## kpack device code

TheRock dist tarballs can be kpack-split: a host library carries a
`.rocm_kpack_ref` marker (msgpack with `kpack_search_paths`) instead of on-disk
device code, and the HIP runtime loads its kernels from an archive such as
`opt/rocm/.kpack/blas_lib_gfx1151.kpack`. Search paths resolve relative to the
library directory, with `@GFXARCH@` replaced by `[payload].gfx_arch`.

After classification, the generator reads every owned ELF's section headers.
For each kpack marker it requires at least one named archive in the scanned
payload, and each present archive must be owned by the library's package or by
one of that package's direct `depends`. Anything else fails as
`KPACK_REF_UNOWNED`, because such a render builds cleanly and then fails at the
first kernel launch.

## Failure codes

The generator exits non-zero if it cannot classify the tree cleanly.

Structured diagnostics are emitted in this shape:

- `UNMAPPED_COMPONENT: <path>`
- `AMBIGUOUS_OWNERSHIP: <path> -> <pkg1>,<pkg2>`
- `NEW_THEROCK_PACKAGE_CLASS: <class> from <path>`
- `MISSING_PACKAGE_METADATA: <pkg>`
- `KPACK_REF_UNOWNED: <library path>`
- `SONAME_DEPEND_UNRESOLVED: <pkg>`

Each failure also includes a short hint explaining whether the fix belongs in:

- path ownership overrides
- component alias mapping
- package metadata definitions
- meta package dependency definitions
- kpack archive ownership and direct package depends
- the staged ELF behind a `soname_depends` entry

## Typical update workflow

1. Build or stage a new TheRock tree that contains every payload package you
   intend to render. For the pinned dist tarball, run
   `python tools/stage_therock_payload.py --stage <staged-root>`, then build
   MIGraphX into it with `tools/stage_migraphx_for_therock.zsh --stage
   <staged-root>`; see `packages/therock-gfx1151/README.md`.
2. Ensure the repo-local `upstream/ai-notes` submodule is initialized and up to
   date for the recipe change you intend to adopt.
3. Run `python tools/render_therock_pkgbase.py --therock-root <staged-root>`.
4. If it fails:
   - add aliases for known new component directories or file prefixes
   - add explicit path ownership overrides for outliers
   - add package metadata if a package name is new
5. Re-run until ownership is total and unambiguous.
6. Build the rendered package base under `packages/therock-gfx1151/`, with
   `_THEROCK_ROOT=<staged-root>` when the payload is not in `/`.
7. Publish refreshed artifacts through the local repo workflow in
   `docs/usage/local-repo.md`.
