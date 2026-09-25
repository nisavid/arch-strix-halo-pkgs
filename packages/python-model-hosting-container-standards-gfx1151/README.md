# python-model-hosting-container-standards-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/aws/model-hosting-container-standards`
- Package version: `0.1.16`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `aur/python-model-hosting-container-standards`
- Authoritative reference package: `aur/python-model-hosting-container-standards`
- Advisory reference packages: `none`
- Applied source patch files/actions: `0`

## Recipe notes

This package supplies the SageMaker handler bootstrap that vLLM's
OpenAI-compatible API server applies to its FastAPI app. vLLM 0.30.0 imports
it while `vllm serve` builds the app, so the server cannot start without it.
It is pure Python, but it belongs in the local package closure because no
Arch sync repo carries it.


## Scaffold notes

- Part of the vLLM API server dependency closure (#110).
- Renders through the Blackcat native-wheel lane in pure-Python mode, like prometheus-fastapi-instrumentator; Blackcat's recipe does not name this package.
- Builds with the Arch poetry-core backend and keeps Python build dependency checking on, because poetry-core >=2.0.0,<3.0.0 is the only build requirement.

## Intentional Divergences

- Tracks upstream model-hosting-container-standards 0.1.16 from PyPI; the vLLM package must not depend on a foreign AUR provider.
- Keeps the package pure-Python and architecture-independent; there are no Strix-specific native flags to carry.
- Carries every upstream runtime requirement from the published metadata (fastapi, starlette, pydantic, jmespath, httpx, setuptools and supervisor); the AUR package lists only fastapi and pydantic.

## Update Notes

- Check vLLM's requirements/common.txt (model-hosting-container-standards >=0.1.14,<1.0.0 at vLLM 0.30.0) and the upstream release together before updating.
- vLLM caps fastapi below 0.137.0 because a FastAPI route-tree change breaks this package's handler overrides. Arch python-fastapi is above that cap; re-check the server smoke after any FastAPI or package update.
- After publishing a rebuilt package, verify `import model_hosting_container_standards.sagemaker` through the installed local Python lane, then rerun the vLLM server smoke, which bootstraps it when the app is built.
- On 2026-09-25, added at 0.1.16 for the generation-C W2A closure (#110, #111). vLLM 0.30.0 imports it at module level in `vllm/entrypoints/serve/sagemaker/api_router.py`, which `vllm/entrypoints/launchers/app.py` imports, so `vllm serve` cannot start without it. It is built in the rootless C build root in the vLLM lease job.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
