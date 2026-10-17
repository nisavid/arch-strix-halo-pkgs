# python-prometheus-fastapi-instrumentator-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/trallnag/prometheus-fastapi-instrumentator`
- Package version: `8.1.0`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `aur/python-prometheus-fastapi-instrumentator`
- Authoritative reference package: `aur/python-prometheus-fastapi-instrumentator`
- Advisory reference packages: `none`
- Applied source patch files/actions: `0`

## Recipe notes

This package supplies the Prometheus metrics middleware that the vLLM
OpenAI-compatible server uses for `/metrics`. It is pure Python, but it
belongs in the local package closure because vLLM 0.30.0 requires
prometheus-fastapi-instrumentator >=8.0.0, and the only Arch-family package
is the AUR 7.0.0 build, which predates Starlette 1.0 support.


## Scaffold notes

- Part of the vLLM API server dependency closure (#110).
- Renders through the Blackcat native-wheel lane in pure-Python mode, like compressed-tensors and Accelerate; Blackcat's recipe does not name this package.
- Builds with the Arch poetry-core backend and keeps Python build dependency checking on, because poetry-core >=2.0 is the only build requirement.

## Intentional Divergences

- Tracks upstream prometheus-fastapi-instrumentator 8.1.0 from PyPI instead of the AUR 7.0.0 baseline, because vLLM 0.30.0 requires >=8.0.0 (v8 unblocks Starlette >=1.0) and the vLLM package must not depend on a foreign AUR provider.
- Keeps the package pure-Python and architecture-independent; there are no Strix-specific native flags to carry.
- Depends on python-gfx1151 so the vLLM server stack stays on the repo-managed Python lane. Upstream requires starlette and prometheus-client only; fastapi is not a runtime requirement of this package.

## Update Notes

- Check vLLM's requirements/common.txt floor (prometheus-fastapi-instrumentator >=8.0.0 at vLLM 0.30.0) and the upstream CHANGELOG together before updating.
- Re-check the upstream runtime requirements (starlette >=1.0.0,<2.0.0 and prometheus-client >=0.8.0,<1.0.0 at 8.1.0) against Arch python-starlette and python-prometheus_client.
- After publishing a rebuilt package, verify `from prometheus_fastapi_instrumentator import Instrumentator` and instrument a minimal FastAPI app through the installed local Python lane, then rerun the vLLM server smoke, which serves `/metrics` through this package.
- On 2026-09-25, added at 8.1.0 for the generation-C W2A closure (#110). It is built later in the rootless C build root with the vLLM package; until then the vLLM server smoke has no >=8 provider.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
