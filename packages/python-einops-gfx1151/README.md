# python-einops-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/arogozhnikov/einops`
- Package version: `0.8.2`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `aur/python-einops`
- Authoritative reference package: `aur/python-einops`
- Advisory reference packages: `none`
- Applied source patch files/actions: `0`

## Recipe notes

This package supplies einops, which vLLM 0.30.0 imports at worker startup and
in several model layers, including the Qwen3.5 and Qwen3.6 gated-delta-net
attention. It is pure Python, but it belongs in the local package closure
because no Arch sync repo carries einops and the AUR package tracks an
unreleased development snapshot.


## Scaffold notes

- Part of the vLLM runtime dependency closure (#110).
- Renders through the Blackcat native-wheel lane in pure-Python mode, like compressed-tensors and prometheus-fastapi-instrumentator; Blackcat's recipe does not name this package.
- Builds with the Arch hatchling backend and keeps Python build dependency checking on, because hatchling >=1.10.0 is the only build requirement.

## Intentional Divergences

- Tracks the upstream einops 0.8.2 PyPI release instead of the AUR package, which packages an unreleased 0.9.0dev snapshot; the vLLM package must not depend on a foreign AUR provider.
- Keeps the package pure-Python and architecture-independent; there are no Strix-specific native flags to carry.
- Depends on python-gfx1151 so the vLLM stack stays on the repo-managed Python lane. Upstream declares no runtime requirements.

## Update Notes

- Check vLLM's requirements/common.txt (einops with no version bound at vLLM 0.30.0) and the upstream release notes together before updating.
- After publishing a rebuilt package, verify `import einops` and a `einops.rearrange` probe on a NumPy array through the installed local Python lane.
- On 2026-09-25, added at 0.8.2 for the generation-C W2A closure (#110, #111). vLLM 0.30.0 imports einops at worker startup (`vllm/model_executor/layers/mamba/ops/ssd_combined.py`, reached from `vllm/v1/worker/utils.py`) and in the Qwen3.5 and Qwen3.6 gated-delta-net layers. It is built in the rootless C build root in the vLLM lease job.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
