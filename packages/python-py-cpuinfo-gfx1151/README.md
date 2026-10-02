# python-py-cpuinfo-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/workhorsy/py-cpuinfo`
- Package version: `9.0.0`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `none`
- Authoritative reference package: `none`
- Advisory reference packages: `none`
- Applied source patch files/actions: `0`

## Recipe notes

This package supplies py-cpuinfo, which vLLM 0.30.0 imports from its usage
module while `vllm serve` starts. It is pure Python, but it belongs in the
local package closure because python-py-cpuinfo is no longer in the Arch sync
repos and no AUR package replaces it.


## Scaffold notes

- Part of the vLLM runtime dependency closure (#110).
- Renders through the Blackcat native-wheel lane in pure-Python mode; Blackcat's recipe does not name this package.
- The sdist has no pyproject.toml, so `python -m build` uses the setuptools legacy backend, which needs setuptools and wheel.

## Intentional Divergences

- Arch carried python-py-cpuinfo 9.0.0 until it left the sync repos, and no AUR package replaces it, so this package takes over the former Arch name through provides and conflicts.
- Keeps the package pure-Python and architecture-independent; there are no Strix-specific native flags to carry.
- Depends on python-gfx1151 so the vLLM stack stays on the repo-managed Python lane. Upstream declares no runtime requirements.

## Update Notes

- Check vLLM's requirements/common.txt (py-cpuinfo with no version bound at vLLM 0.30.0) and the upstream release notes together before updating.
- After publishing a rebuilt package, verify `import cpuinfo` and `cpuinfo.get_cpu_info()` through the installed local Python lane.
- On 2026-09-25, added at 9.0.0 for the generation-C W2A closure (#110, #111). vLLM 0.30.0 imports cpuinfo from `vllm/usage/usage_lib.py`, which `vllm serve` imports at startup. It is built in the rootless C build root in the vLLM lease job.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
