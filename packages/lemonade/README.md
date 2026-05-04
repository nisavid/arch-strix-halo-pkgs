# lemonade

## Maintenance Snapshot

- Role: `meta-package`
- Optional backends:
  - `llama.cpp-hip-gfx1151`
  - `llama.cpp-vulkan-gfx1151`
- Recipe package key: `lemonade`
- Scaffold template: `meta-package`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/lemonade-sdk/lemonade.git`
- Package version: `10.3.0`
- Recipe revision: `a1d7a68 (20260427, 16 patch commits)`
- Recipe steps: `34, 35, 36`
- Recipe dependencies: `therock, llamacpp`
- Recorded reference packages: `aur/lemonade-server, aur/lemonade-desktop`
- Authoritative reference package: `none`
- Advisory reference packages: `aur/lemonade-server, aur/lemonade-desktop`
- Applied source patch files/actions: `0`

## Recipe notes

Lemonade is a unified inference server wrapping llama.cpp (GPU/CPU),
FLM (NPU), and ONNX backends behind an OpenAI-compatible API.

The project split in v10: the git repo (v10.0.0) is a C++ server,
while the Python SDK is published separately as lemonade-sdk on PyPI
(v9.1.4). The SDK handles llama-server process management, model
downloads, .env loading, and hardware detection.

Version pin fixes: lemonade-sdk pins huggingface-hub==0.33.0,
onnx==1.18.0, transformers<=4.53.2 which conflict with vLLM.
Reinstalling at compatible versions resolves conflicts.

## Scaffold notes

- Meta package for server, app, and both llama.cpp backend packages.
- Keep routing logic out of this package; it is a convenience install only.

## Intentional Divergences

- This is a convenience meta package for the full local Lemonade plus packaged llama.cpp backend experience.
- It intentionally does not encode backend routing logic; that belongs in runtime policy, not package dependencies.

## Update Notes

- Keep this meta package aligned with the intended first-pass user story and revisit its dependency set after benchmarking determines whether both packaged llama.cpp backends remain worth shipping.
- Do not let this meta package obscure the standalone update story for lemonade-server, lemonade-app, or the backend packages.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
