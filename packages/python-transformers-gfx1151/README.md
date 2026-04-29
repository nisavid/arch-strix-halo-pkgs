# python-transformers-gfx1151

## Maintenance Snapshot

- Package origin: local closure package
- Build method: `python -m build`
- Upstream repo: `https://github.com/huggingface/transformers`
- Upstream version: `5.7.0`
- Recorded reference packages: `cachyos/python-transformers, extra/python-transformers`
- Authoritative reference package: `cachyos/python-transformers`
- Advisory reference packages: `extra/python-transformers`
- Applied source patch files/actions: `0`

## Why This Package Exists

The host `python-transformers 5.2.0-1` package did not ship
`transformers.models.gemma4`, which blocked local Gemma 4 safetensors smoke
tests in vLLM even after the ROCm platform-detection fixes were in place.

Published upstream wheels first expose `gemma4` in the `5.5.x` lane, so this
repo carries a local closure package to keep the stack pacman-installable and
Gemma-4-capable without waiting on distro repo timing.

## Intentional Divergences

- Tracks upstream `transformers 5.7.0` from PyPI instead of the currently
  installed CachyOS `5.2.0-1` lane because Gemma 4 support is missing from the
  older package.
- Keeps the package pure-Python and architecture-independent; there are no
  applicable Strix-specific native optimization flags to carry here.
- Depends explicitly on `python-numpy-gfx1151` and `python-gfx1151` so the
  local inference stack stays on the repo-managed Python lane.

## Update Notes

- Before updating, verify the candidate Transformers release actually ships
  `transformers.models.gemma4`; do not assume the version number alone is
  enough.
- On 2026-04-23, reviewed upstream Transformers `5.6.2`. The `5.6.0..5.6.2`
  range fixes `flash_attention_forward` when `s_aux` is absent, improves
  fine-grained FP8 kernel error handling, and repairs Qwen3.5 MoE conversion
  mapping while keeping `transformers.models.gemma4` present. The package
  remains pinned to the validated `5.7.0` Gemma 4 closure lane until a
  Transformers/Gemma update arc reruns the host smokes.
- Re-check dependency metadata against the chosen baseline package and the
  published PyPI metadata. The package is intentionally thin and should not
  grow optional extras into hard runtime dependencies.
- After any update, rerun the Gemma 4 vLLM smoke test on the host rather than
  stopping at `import transformers`.
