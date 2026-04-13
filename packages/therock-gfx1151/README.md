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
python tools/render_therock_pkgbase.py --recipe-root /path/to/ai-notes
```

That command:

- scans the staged or installed `opt/rocm` tree
- computes `pkgver` from the recipe repo history for `strix-halo/`
- stamps recipe provenance into the generated `PKGBUILD`
- rewrites the file lists and manifest in this directory

## Build expectation

The generated `PKGBUILD` expects `_THEROCK_ROOT` to point at a filesystem root
that contains `opt/rocm`. For a live local tree, `_THEROCK_ROOT=/` is valid.
For a staged install tree, point it at that staging root instead.
