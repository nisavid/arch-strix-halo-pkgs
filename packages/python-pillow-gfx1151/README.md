# python-pillow-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/python-pillow/Pillow`
- Package version: `12.2.0`
- Recipe revision: `a1d7a68 (20260427, 16 commits touching recipe path)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-pillow`
- Authoritative reference package: `extra/python-pillow`
- Advisory reference packages: `none`
- Applied source patch files/actions: `0`

## Recipe notes

This package is the Pillow output from the shared `native_wheels` recipe
phase. That phase also builds numpy, sentencepiece, zstandard, asyncpg,
duckdb, PyYAML, psutil, uvloop, httptools, msgspec, aiohttp, multidict,
yarl, and frozenlist from source with Zen 5 optimization flags, but those
outputs are tracked as separate packages or follow-up package lanes rather
than as dependencies of `python-pillow-gfx1151`.

Pillow covers image preprocessing for multimodal model and corpus-enrichment
paths. The package keeps Arch's image-library dependency shape while moving
the native extension onto the local amdclang native-wheel lane.


## Scaffold notes

- Part of the core Blackcat model/config stack and consumed by the local Mistral Common and TorchVision packages.
- Use the shared native-wheel renderer so amdclang, path remapping, and Zen 5 flags stay aligned with the other native wheel packages.

## Intentional Divergences

- Follows Arch's Pillow package shape while rebuilding the native extension through the Blackcat native-wheel compiler lane.
- Uses the current Arch/PyPI 12.2.0 release instead of the older Blackcat recipe example pin because this package is a normal Arch-facing local replacement.

## Update Notes

- Check Arch first for image-library dependency and optional-integration drift before updating.
- After publishing a rebuilt package, verify `from PIL import Image` and a tiny in-memory image round trip through the installed local Python lane.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
