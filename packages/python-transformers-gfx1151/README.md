# python-transformers-gfx1151

## Maintenance Snapshot

- Package origin: local closure package
- Build method: `python -m build`
- Upstream repo: `https://github.com/huggingface/transformers`
- Upstream version: `5.8.1`
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

- Tracks upstream `transformers 5.8.1` from PyPI so the local vLLM closure
  stays ahead of distro timing for Gemma, Qwen, and model-surface fixes.
- Keeps the package pure-Python and architecture-independent; there are no
  applicable Strix-specific native optimization flags to carry here.
- Depends explicitly on `python-numpy-gfx1151`, `python-safetensors-gfx1151`,
  `python-tokenizers-gfx1151`, `python-pyyaml-gfx1151`, and
  `python-gfx1151` so the local inference stack stays on the repo-managed
  Python and model-loading closure.

## Update Notes

- Before updating, verify the candidate Transformers release actually ships
  `transformers.models.gemma4`; do not assume the version number alone is
  enough.
- The current package adopts `5.8.1` with DeepSeek V4 serving and weight
  conversion fixes while keeping `transformers.models.gemma4` present.
- Run build and install commands through `/usr/bin/python` in the PKGBUILD so
  package bytecode generation does not inherit agent-local Python wrappers or
  private pycache paths from the maintainer environment.
- Re-check dependency metadata against the chosen baseline package and the
  published PyPI metadata. The package is intentionally thin and should not
  grow optional extras into hard runtime dependencies.
- After any update, rerun the Gemma 4 vLLM smoke test on the host rather than
  stopping at `import transformers`.
