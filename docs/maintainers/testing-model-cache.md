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

- `Qwen/*`
- `RedHatAI/*`
- `google/*`

Move model or dataset entries from those namespaces out of the end-user
Hugging Face cache when they are present there. Copy, rather than move, other
Hugging Face entries that this repo uses so end-user workflows keep their
existing cache entries.

Current kept model IDs include:

- `AXERA-TECH/Qwen3-4B-GPTQ-Int4`
- `Dogacel/specdrift-qwen3.6-35b-a3b-eagle3`
- `Qwen/Qwen3.5-0.8B`
- `Qwen/Qwen3.6-35B-A3B`
- `RedHatAI/Qwen3.6-35B-A3B-NVFP4`
- `google/gemma-4-26B-A4B-it`
- `google/gemma-4-E2B-it`
- `surogate/Qwen3.5-0.8B-FP8`
- `z-lab/Qwen3.6-35B-A3B-DFlash`
- `zeroentropy/zembed-1`
- `zeroentropy/zerank-2`

Keep the AXERA Int4 repository as an operator-selected cache artifact, not as a
drop-in replacement for the older vLLM GPTQ safetensors smoke. Its published
files are AXERA runtime artifacts rather than an ordinary vLLM GPTQ checkpoint.
Add a separate runnable vLLM GPTQ scenario only after choosing a compatible
checkpoint.

The vLLM pooling and Lemonade GGUF pooling surfaces intentionally do not use the
ZeroEntropy repositories. `intfloat/multilingual-e5-small` exercises vLLM
embedding pooling and FlexAttention behavior, `jinaai/jina-reranker-v3`
exercises vLLM score/rerank behavior with the Jina ranking head, and the
Lemonade pooling scenarios exercise registered GGUF model paths. Replacing
those with `zeroentropy/zembed-1` or `zeroentropy/zerank-2` would change the
runtime interface under test.

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
