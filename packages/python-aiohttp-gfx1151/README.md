# python-aiohttp-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/aio-libs/aiohttp`
- Package version: `3.14.5`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-aiohttp`
- Authoritative reference package: `extra/python-aiohttp`
- Advisory reference packages: `none`
- Applied source patch files/actions: `0`

## Recipe notes

This package is the aiohttp output from the shared `native_wheels` recipe
phase. That phase also builds numpy, sentencepiece, zstandard, asyncpg,
duckdb, PyYAML, psutil, Pillow, uvloop, httptools, msgspec, multidict, yarl,
and frozenlist from source with Zen 5 optimization flags. `multidict`, `yarl`,
and `frozenlist` are direct local dependencies of this package; the remaining
outputs are tracked as separate packages or follow-up package lanes rather than
as dependencies of `python-aiohttp-gfx1151`.

aiohttp supplies async HTTP client/server helpers used by service paths. The
local package follows Arch's system-dependency shape with
AIOHTTP_USE_SYSTEM_DEPS=1 while moving its native extensions onto the local
amdclang native-wheel lane.


## Scaffold notes

- Part of the comprehensive Blackcat service/runtime wheel stack and consumed by the local vLLM package.
- Keep dependencies pointed at the local frozenlist, multidict, and yarl packages so the aiohttp closure stays on the repo-owned optimized stack.

## Intentional Divergences

- Follows Arch's python-aiohttp system-dependency package shape while rebuilding native extensions through the Blackcat native-wheel compiler lane.
- Keeps async HTTP client/server helpers for vLLM/FastAPI service paths on the repo-owned optimized wheel stack.

## Update Notes

- Check Arch first for llhttp, Cython, and dependency metadata before updating.
- Keep AIOHTTP_USE_SYSTEM_DEPS=1 in the build environment unless upstream changes how system llhttp is selected.
- After publishing a rebuilt package, verify `import aiohttp` and a minimal ClientSession construction path through the installed local Python lane.
- On 2026-09-22, update to aiohttp 3.14.3 for the generation-C W2A closure (#110), built in the rootless C build root against TheRock 7.14.1 and python-gfx1151 3.14.7.
- On 2026-10-11, update to aiohttp 3.14.5 in generation C's model closure move (#183), by owner decision under the version freeze's security exception. 3.14.4 is the first patched release for eight advisories that upstream published on 2026-10-07 (GHSA-9xw5-w5jj-pvcg, GHSA-2g87-pp6c-29x5, GHSA-f9xw-jh8m-3mwq, GHSA-494j-54xm-rwp3, GHSA-5wr8-gcqf-gqf3, GHSA-6cjc-53gc-5rqm, GHSA-gx76-c99x-2c96 and GHSA-pqxq-w44r-73xw), and 3.14.5 adds a WebSocket bug fix. By advisory title, the cookie and connector-pool ones (GHSA-494j-54xm-rwp3, GHSA-6cjc-53gc-5rqm, GHSA-gx76-c99x-2c96) concern the aiohttp client, which vLLM uses to fetch request-supplied media; the others concern an aiohttp server, which vLLM does not run, or were not classified. 3.14.5 requires yarl >=1.25.1,<2.0 and multidict >=4.5,<8.0, which python-yarl-gfx1151 1.25.1 and python-multidict-gfx1151 6.9.1 meet. Arch extra python-aiohttp was still 3.14.3-1 on that date, with the same depends, so this package is ahead of its Arch reference until Arch moves.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
