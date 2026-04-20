# TheRock ROCm Split Package Base

This directory is the canonical rendered package base for the local TheRock
ROCm split.

It is generated from:

- `generators/therock_split.py`
- `policies/therock-packages.toml`
- `templates/PKGBUILD.in`

## Refresh

Run:

```bash
python tools/render_therock_pkgbase.py --therock-root <staged-root>
```

That command:

- scans the staged or installed `opt/rocm` tree
- uses `pkgver` from `policies/therock-packages.toml`
- stamps repo-local `upstream/ai-notes/strix-halo` recipe provenance into the
  generated `PKGBUILD` and manifest
- rewrites the file lists and manifest in this directory

## Build expectation

The generated `PKGBUILD` expects `_THEROCK_ROOT` to point at a filesystem root
that contains `opt/rocm`. For a complete live local tree, `_THEROCK_ROOT=/` is
valid. For a staged install tree, point it at that staging root instead.

## rocm-core baseline

`rocm-core-gfx1151` now treats CachyOS `rocm-core` as the distro-integration
baseline while still packaging the newer TheRock 7.13 payload.

That means the split package intentionally carries the small Cachy-style
integration surface on top of the scanned TheRock files:

- `etc/ld.so.conf.d/rocm.conf`
- shell path setup in `etc/profile.d/rocm.sh` and
  `usr/share/fish/vendor_conf.d/rocm.fish`
- the `opt/rocm/bin/rdhc` wrapper plus `opt/rocm/share/rdhc/*`
- license copies under `opt/rocm/share/doc/rocm-core/` and
  `usr/share/licenses/rocm-core/`

The remaining file-list delta against Cachy should be TheRock-owned additions
or version-lane differences only: `nlohmann` headers, `.hipInfo`,
`share/modulefiles`, `share/therock`, and the expected `rocmCoreTargets` /
`librocm-core.so` version suffix changes.
