# Testing Model Cache

This repo exercises Hugging Face model and dataset repositories as validation
fixtures. Keep testing fixtures separate from end-user model caches so package
validation does not consume interactive model-storage capacity.

## Cache Contract

Use a dedicated Hugging Face Hub cache for repo validation work. Agents and
operator scripts that download, serve, inspect, or validate Hugging Face models
for this repo must set:

```sh
HF_HUB_CACHE=<testing HF hub cache root>
```

Use `HF_HUB_CACHE` rather than `HF_HOME` for the testing cache. It points
directly at the Hub cache root and avoids changing unrelated Hugging Face state
such as tokens, assets, or Xet chunk caches.

Do not commit the concrete local testing-cache path. Local mount points and
cache roots are private host context. Keep exact paths in ignored session
artifacts or operator-local configuration only.

## Model Placement

The testing cache owns repo validation fixtures for these namespaces:

- `Dogacel/*`
- `Qwen/*`
- `RedHatAI/*`
- `google/*`
- `surogate/*`
- `z-lab/*`
- `zeroentropy/*`

Move `Qwen/*`, `RedHatAI/*`, and `google/*` model or dataset entries out of the
end-user Hugging Face cache when they are present there. Copy, rather than move,
other retained entries that this repo uses so end-user workflows keep their
existing cache entries.

Current kept model IDs include:

- `Dogacel/specdrift-qwen3.6-35b-a3b-eagle3`
- `Qwen/Qwen3.5-0.8B`
- `Qwen/Qwen3.5-35B-A3B-GPTQ-Int4`
- `Qwen/Qwen3.6-35B-A3B`
- `RedHatAI/Qwen3.6-35B-A3B-NVFP4`
- `google/gemma-4-26B-A4B-it`
- `google/gemma-4-E2B-it`
- `surogate/Qwen3.5-0.8B-FP8`
- `z-lab/Qwen3.6-35B-A3B-DFlash`
- `zeroentropy/zembed-1`
- `zeroentropy/zerank-2`

Keep `Qwen/Qwen3.5-35B-A3B-GPTQ-Int4` as the retained GPTQ Int4 safetensors
target. It replaces the rejected RafaDom Claude-derived GPTQ fixture and the
AXERA Int4 repository, whose files target AXERA's runtime format rather than an
ordinary vLLM GPTQ checkpoint.

The vLLM pooling scenarios use the same retained ZeroEntropy repositories as
the Transformers ZeroEntropy scenarios. `zeroentropy/zembed-1` exercises
vLLM's causal-LM-to-embedding adapter with the SentenceTransformers last-token
pooling and normalization metadata. `zeroentropy/zerank-2` exercises vLLM's
causal-LM-to-classification adapter by deriving a one-label classifier from the
`Yes` token and preserving the model-card score scaling. The Lemonade pooling
scenarios remain separate because they exercise registered GGUF model paths.

Update this list when tracked scenarios add or remove model IDs. Keep model
bindings in docs as model IDs plus placeholder cache roots, not concrete
snapshot paths.

## Cache Portability

Hugging Face Hub cache repository directories are self-contained when copied or
moved as complete `models--...` or `datasets--...` directories. Each repository
directory carries its own `refs/`, `snapshots/`, and `blobs/` subdirectories;
snapshot entries are relative symlinks into that repository's `blobs/`
directory when symlinks are supported.

Prefer whole repository-directory migration over per-blob surgery. Do not
replace main-cache blob files with symlinks into the testing cache until the
affected runtime surfaces have been validated against that layout.
