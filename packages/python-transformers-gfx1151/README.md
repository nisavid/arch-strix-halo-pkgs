# python-transformers-gfx1151

## Maintenance Snapshot

- Package origin: local closure package
- Build method: `python -m build`
- Upstream repo: `https://github.com/huggingface/transformers`
- Upstream version: `5.18.0`
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

- Tracks upstream `transformers 5.18.0` from PyPI so the local vLLM closure
  stays ahead of distro timing for Gemma, Qwen, and model-surface fixes.
- Keeps the package pure-Python and architecture-independent; there are no
  applicable Strix-specific native optimization flags to carry here.
- Depends explicitly on `python-numpy-gfx1151`, `python-safetensors-gfx1151`,
  `python-tokenizers-gfx1151`, `python-pyyaml-gfx1151`, and
  `python-gfx1151` so the local inference stack stays on the repo-managed
  Python and model-loading closure.
- Declares the huggingface-hub range from the packaged metadata as versioned
  depends, `python-huggingface-hub>=1:1.31.0` and
  `python-huggingface-hub<1:3`; the CachyOS baseline declares only a floor.
  Transformers checks that range when it is imported, so pacman must refuse a
  hub release outside it instead of leaving `import transformers` to fail.
  Arch packages huggingface-hub under epoch 1, so both bounds carry the epoch.

## Update Notes

- Before updating, verify the candidate Transformers release actually ships
  `transformers.models.gemma4`; do not assume the version number alone is
  enough.
- The current package adopts `5.18.0` for generation C's model closure
  (#183). `5.16.1` and `5.17.0` require `huggingface-hub<2.0` and fail at
  import next to Arch's huggingface-hub 2.x; `5.18.0` requires
  `huggingface-hub>=1.31.0,<3.0`. Its other runtime requirements match
  `5.16.1`: `numpy>=1.17`, `packaging>=20.0`, `pyyaml>=5.1`,
  `regex>=2025.10.22`, `safetensors>=0.8.0`, `tokenizers>=0.23.1,<0.24.0`,
  `tqdm>=4.60` and `typer`. It keeps `transformers.models.gemma4` present.
- vLLM 0.30.0 `pixtral.py` imports symbols that Transformers 5.17 removed, so
  `5.18.0` needs the `pixtral.py` hunk of vLLM #56108 in
  `python-vllm-rocm-gfx1151` before the 11 pixtral-chain model modules
  import. Generation C serves none of them.
- When the packaged metadata changes its huggingface-hub range, change both
  versioned depends with it and keep the epoch.
  `tools/buildroot/model-closure.targets` floors the same pair for the
  generation-C build root.
- Run build and install commands through `/usr/bin/python` in the PKGBUILD so
  package bytecode generation does not inherit agent-local Python wrappers or
  private pycache paths from the maintainer environment.
- Re-check dependency metadata against the chosen baseline package and the
  published PyPI metadata. The package is intentionally thin and should not
  grow optional extras into hard runtime dependencies.
- After any update, rerun the Gemma 4 vLLM smoke test on the host rather than
  stopping at `import transformers`.
