# Lemonade Live Validation

This page maps the live-validation bar for the standalone Lemonade family
(`lemonade`, `lemonade-server`, `lemonade-app`, `llama.cpp-hip-gfx1151`, and
`llama.cpp-vulkan-gfx1151`) to tracked scenarios. Run it after the family is
built, published, and installed on the host. Record the results in
[Current State](current-state.md), keeping the built, installed, installed-smoked,
and live-validated states separate.

The scenarios are in `inference/scenarios/lemonade-live-validation.toml`. The
work is tracked in issue #138.

## Coverage

| Bar item | Scenario or check |
| --- | --- |
| GGUF text on HIP, direct | `llama.cpp.hip.qwen3-0.6b-q8-0.completion` |
| GGUF text on Vulkan, direct | `llama.cpp.vulkan.qwen3-0.6b-q8-0.completion` |
| GGUF text on HIP, via Lemonade | `lemonade.llamacpp.rocm.qwen3-0.6b-q8-0.completion` |
| GGUF text on Vulkan, via Lemonade | `lemonade.llamacpp.vulkan.qwen3-0.6b-q8-0.completion` |
| Start and restart with config preserved; HIP discovery | `lemonade.lifecycle.restart-config-hip-discovery` |
| Pin persistence and startup restore | `lemonade.pins.persistence-startup-restore` |
| Budget admit and refuse, with APU GTT counted | `lemonade.budget.gtt-admit-refuse` |
| Pinned and in-use models never displaced | `lemonade.residency.pinned-busy-not-displaced` |
| Package provenance; no silent downloader, bundled-backend fallback, or foreign or mixed package | `lemonade.provenance.family-no-fallback` |
| No fetch on `/load`, inference auto-load, or Ollama auto-load: journal, cache-diff, and network evidence, plus a registered but absent model that fails loudly on each path | `lemonade.nofetch.preplaced-load-missing-model` |
| The service keeps the consumer models `zembed-1` Q4_K_M and `zerank-2` Q8_0 pinned and loaded | `lemonade.pins.service-consumer-pins` |
| The service answers chat with the pinned qwen35moe user model, and the pin stays loaded with no load error | `lemonade.chat.pinned-user-model.qwen35moe` |
| Embeddings, both rerankers, and selected-logit | the existing `lemonade.pooling.*` and `lemonade.reranking.zerank-2.selected-logit` scenarios |
| App launch with pin and startup controls, plus one text interaction | the `lemonade.app.pin-startup-text` operator checklist in the same TOML file |
| Kokoro TTS and the app's TTS interaction | deferred to generation C W2B (#113); see below |

All four text scenarios use the same file:
`Qwen/Qwen3-0.6B-GGUF` at revision `23749fefcc72300e3a2ad315e1317431b06b590a`,
`Qwen3-0.6B-Q8_0.gguf`. Every scenario that exercises it checks the file's
SHA-256 against the pinned digest before reporting success. The direct and
isolated scenarios hash the bound file. The service scenarios require the exact
`Qwen/Qwen3-0.6B-GGUF:Q8_0` checkpoint and hash the service's resolved main
file, so the runner must be able to read that file. The Lemonade scenarios also
compare the backend
process's executable against `pacman -Qo`, so they fail if Lemonade serves the
model from anything other than the packaged llama.cpp.

## Loaded-Library Provenance

A packaged executable is not enough: with `backend=rocm`, `lemond` prepends
cached TheRock library directories to the backend's `LD_LIBRARY_PATH`, so a
cached runtime can shadow the packaged one. After the completion, while the
backend `llama-server` is still running, the Lemonade text scenarios and the
no-fetch pre-placed phase read `/proc/<pid>/maps`. They select every mapped
ROCm, HIP, ggml, llama, or mtmd shared object and require:

- none of them lies under `lemond`'s cache `bin/` directory;
- each one resolves to an owner with `pacman -Qo`;
- every owner is listed in the local repo (`pacman -Slq strix-halo-gfx1151`);
- the ggml, llama, and mtmd objects are owned by the selected backend package; and
- the ROCm backend maps the HIP runtime (`libamdhip64`).

Output reports counts, package names, and the backend executable's file name
only, never library or cache paths.
Reading another user's `maps` needs the same privileges as reading that
process's memory map, so run these scenarios with access to the service's
processes; otherwise they fail with `backend_maps_unreadable`.

## Scenario Classes

- `mutates-service`: loads and unloads the test model on the running
  `lemond.service`. It unloads the model on exit if the model was not already
  resident. It never changes pins or config.
  - Exception: the pinned-chat scenario never unloads. Its one service change
    is the chat request's implicit load of a model that is already pinned and
    downloaded, which leaves the pinned model resident as the service intends.
    When the model was not resident, that load can displace other unpinned
    models. Otherwise it reads only the service's `/pins`, `/models/<id>`,
    `/models/<id>/files`, and `/health`, the header of the model's GGUF file,
    and the backend's `/proc/<pid>/cmdline`.
- `isolated-lemond`: starts a private `lemond` from `/usr/bin/lemond` with a
  temporary cache directory. The config is offline, backend fetching is
  disabled, and the packaged llama.cpp backends are used. The scenario reaches
  the test GGUF through a temporary `extra_models_dir`. The service's pins and
  config are never touched, and the temporary state is removed on exit. These
  scenarios still load models on the shared GPU.
- `read-only`: the provenance scenario only reads pacman, systemd, and the
  service's `/internal/config`. The consumer-pins scenario only reads the
  service's `/pins`, `/health`, and `/models/<id>`.

The pins, budget, and displacement scenarios use an isolated `lemond` rather
than the service. Each one pins and unpins models, changes
`max_gpu_memory_occupancy_gb`, restarts `lemond`, or needs a one-slot
configuration so that it can force a displacement. On the service, those steps
would rewrite the host's `config.json` and `pinned_models`. They would also
unload models that clients are using. The isolated `lemond` runs the same
packaged binary and backends. Its private config makes the admission and
displacement results deterministic. The service's own pins are checked
read-only by `lemonade.pins.service-consumer-pins`.

## Pinned Chat Model

`lemonade.chat.pinned-user-model.qwen35moe` guards the chat path of the host's
pinned qwen35moe model.
lemonade-server 11.7.0-1 merged the qwen35 and qwen35moe architecture default
`--chat-template-kwargs '{"preserve_thinking":true}'` into the global
llama.cpp args in a way that kept the single quotes. llama-server then failed
to parse the JSON and exited, so no qwen35 or qwen35moe model could load.
11.7.0-2 carries patch 0005 (see [Patch Inventory](../patches.md)).

The scenario runs `tools/lemonade_live_smoke.py pinned-chat` against the
running service:

1. `GET /api/v1/pins` must list the model, and `GET /api/v1/models/<id>` must
   report `downloaded: true` (`chat_model_pinned_ok`). Otherwise the scenario
   fails before it sends a chat request, so it never loads an unpinned model
   or starts a download.
2. The model must use the `llamacpp` recipe, and the `general.architecture`
   key in the header of its main GGUF file must be `qwen35` or `qwen35moe`
   (`chat_model_architecture <arch>`, then `chat_model_architecture_ok`). The
   tool finds the file through `GET /api/v1/models/<id>/files?include_paths=true`
   and never prints its path. The model id proves nothing, so this check
   covers any `--chat-model` or `LEMONADE_PINNED_CHAT_MODEL` override. It
   fails closed: an unreadable, truncated, or non-GGUF file, or a header
   without the key, fails with `chat_model_architecture_unverified` before
   the chat request.
3. `POST /api/v1/chat/completions` with one user message and a
   `max_tokens` budget of 1024 must return `finish_reason: "stop"` and a
   non-empty `content` or `reasoning_content` (`chat_completion_ok`). A
   thinking model fills a small budget with reasoning: a 16-token probe ends
   with `finish_reason: "length"` and empty `content`. The tool refuses a
   budget below 512.
4. The model's backend process, found through `/health`, must receive a JSON
   object with `"preserve_thinking": true` after `--chat-template-kwargs` in
   its `/proc/<pid>/cmdline` (`chat_template_kwargs_json_ok`). That value
   comes only from the qwen35 and qwen35moe architecture default after it
   merges with the global args. A quoted value, other JSON, a missing flag, or
   an unreadable cmdline fails. On 11.7.0-1 the load itself fails, so the
   scenario already fails at step 3; this check also catches a quoted value
   when a backend tolerates it.
5. `GET /api/v1/pins` must then report the model as loaded with no
   `load_error` (`pinned_chat_model_loaded_ok`, then `pinned_chat_ok`).

The model id is chosen per host at run time. The default is
`Qwen3.6-35B-A3B-MTP-GGUF-UD-Q4_K_XL`. Pass `--chat-model <id>` to the tool,
or set `LEMONADE_PINNED_CHAT_MODEL=<id>` in the environment of
`tools/run_inference_scenarios.py`, which the scenario inherits. The catalog
does not pin the id. Step 2 rejects an override that is not a qwen35 or
qwen35moe GGUF. Pin and provision that model in the service config before
the window.

## No-Fetch Evidence

On the frozen Lemonade candidate `3d5991033`, `offline: true` does not stop an
implicit auto-pull. Three request paths download a registered model that is not
cached before they load it:

| Path | Request the scenario sends | Phase names |
| --- | --- | --- |
| `/load` | `POST /api/v1/load` with `model_name` | `preplaced_load`, `missing_load` |
| Inference auto-load | `POST /api/v1/chat/completions` naming a model that is not loaded | `preplaced_inference`, `missing_inference` |
| Ollama auto-load | `POST /api/chat` (at the server root) naming `<model>:latest`; `lemond` strips `:latest` | `preplaced_ollama`, `missing_ollama` |

`lemonade.nofetch.preplaced-load-missing-model` runs each path twice against
the service: once for a registered but absent model and once for the
pre-placed test GGUF. The three missing phases run first, then the three
pre-placed phases. Each phase collects three kinds of evidence and prints its
own markers, prefixed with the phase name:

- Journal: `journalctl -u lemond.service` over the phase window. The window
  must show a line naming the phase's model, which proves that the journal is
  readable. In a pre-placed phase, the window must contain no download or
  install lines. In a missing phase, a download line is the blackholed attempt
  and is recorded, not failed, until the upstream offline refusal lands (see
  below).
- Journal window: the six windows are contiguous and bounded by journal
  cursors, not timestamps. The first window starts after the newest entry when
  the scenario's first phase begins. Each later window starts at the previous
  window's end cursor, so every journal line is charged to exactly one phase.
  A window closes once the phase's own line has landed. The last missing
  window and the last pre-placed window then stay open until the journal has
  been quiet for a settle period (three seconds by default), for at most the
  journal timeout (ten seconds by default) after the phase's own line. A line that lands after its own window closed
  is charged to the next phase. Because the missing phases run first and the
  last one settles, a late attempt from a missing phase can only land in a
  later missing window, where it is recorded, or in a pre-placed window, where
  it fails the scenario. A late line from a pre-placed phase can never be
  recorded as an allowed attempt.
- Caches: the model cache and the backend cache (`<cache dir>/bin`) are listed
  before and after the phase. Every path, type, size, mtime, and symlink target
  must match. The model cache path comes from the service's `/system-info`
  `model_storage.path`. The cache dir comes from `lemond`'s argv, then
  `LEMONADE_CACHE_DIR`, then the service user's `~/.cache/lemonade`.
- Network: `ss -tanp` is sampled throughout the phase, including its settle
  period. No socket owned by `lemond` or its children may have a non-loopback
  peer. In the pre-placed
  phases, none may connect to the download blackhole's port either.
  Connections accepted on one of `lemond`'s listening ports are client
  traffic, such as LAN consumers, and are ignored.

The pre-placed phases are strict. `preplaced_load` loads and completes with
the test GGUF, using the same checks as the text scenario. `preplaced_inference`
and `preplaced_ollama` must auto-load the model: the request must succeed and
leave the model resident, and each prints `<phase>_autoload_ok`. Any download
or install line, cache change, non-loopback connection, or blackhole connect
fails the phase. Every path must really auto-load, so the scenario unloads the
test model after each pre-placed phase. When the model was resident before the
scenario, it is unloaded before the pre-placed phases and reloaded with its
previous recipe options once they finish; only then does the scenario print
`preplaced_residency_restored`, so the catalog does not assert that marker.
If that reload fails after the pre-placed phases passed, the scenario fails.
The reload fails when the model is not resident afterward, or when its `/load`
or `/health` request raises, for example because `lemond` restarted. If a
pre-placed phase already failed, the scenario prints
`preplaced_residency_restore_failed: ...` and reports the phase's own failure,
so the restore error never hides the no-fetch evidence.

The missing phases need a model the candidate registers but has not
downloaded. The default is `Tiny-Test-Model-GGUF`, a small `llamacpp` model in
the candidate's built-in catalog. A host may already have it, so the id is
chosen per host at run time: pass `--missing-model <id>` to
`tools/lemonade_live_smoke.py nofetch`, or set
`LEMONADE_NOFETCH_MISSING_MODEL=<id>` in the environment of
`tools/run_inference_scenarios.py`, which the scenario inherits. The catalog
does not pin the id. To pick one before the run, list the registered models
with `GET /api/v1/models?show_all=true` and choose a small `llamacpp` entry
that reports `downloaded: false`. Before anything is loaded, `GET
/api/v1/models/<id>` must return a status below 400
(`missing_model_registered_ok`), so each phase really reaches the offline
download path, and it must report `downloaded: false`
(`missing_model_absent_ok`). A missing phase passes when all of these hold:

- the request fails loudly, with status >= 400 or an explicit error, and the
  model does not become resident (`<phase>_refused_ok`);
- the model and backend caches are unchanged; and
- `lemond` and its children made no non-loopback connection.

The blackhole stops the bytes, but the attempt is logged, for example as
`Model not cached, downloading from Hugging Face...`. Under the lead's ruling
for #138, a logged, blackholed attempt in a missing phase is an observation,
not a failure. The phase prints `<phase>_blackholed_fetch_attempt_recorded`
with the log-line and blackhole connect counts. Each phase prints either that
marker or `<phase>_no_fetch_log_ok`, never both. When the fork refuses these requests offline
(nisavid/lemonade#155), the missing phases print `<phase>_no_fetch_log_ok`
again, and the recorded marker disappears.

Preconditions are checked before anything is loaded. The service config must
have `offline` and `no_fetch_executables` set to true. `HF_ENDPOINT` and
`MODELSCOPE_ENDPOINT` must both name loopback endpoints. `ss -p` must be able
to attribute the service's listening socket to `lemond`.

Output never names a cache path or another host-specific path. Evidence is
reported as counts. In the no-fetch scenario's refusal and auto-load failure
text, a path under the model cache, the backend cache, or the cache dir becomes
`<model_cache>`, `<backend_cache>`, or `<lemonade_cache>`. Every other printed
refusal, client error, and command error, and the one-line `error:` report that
replaces a traceback when a check fails, turns any absolute path into `<path>`.
The only paths printed are package-owned `/usr/bin` paths, such as
`/usr/bin/lemond` in the provenance scenario.

All of these scenarios carry `validation-window`. Broad selections skip them,
so select them explicitly:

```bash
python tools/run_inference_scenarios.py --tag validation-window \
  --model-path Qwen/Qwen3-0.6B-GGUF=<testing HF hub cache>/models--Qwen--Qwen3-0.6B-GGUF/snapshots/<revision>/Qwen3-0.6B-Q8_0.gguf
```

`--include-validation-window` adds them to an `--engine` or `--model`
selection. `--scenario <id>` always selects the named scenario.

## Operator Inputs

- Download the GGUF into the testing Hugging Face cache described in
  [Testing Model Cache](testing-model-cache.md), and bind it with
  `--model-path`. The direct and isolated scenarios never download anything.
- Register the same checkpoint with the service before the window, as a
  deliberate step:

  ```bash
  lemonade pull user.Qwen3-0.6B-Q8_0-GGUF --checkpoint main Qwen/Qwen3-0.6B-GGUF:Q8_0 --recipe llamacpp
  ```

  The text scenarios fail with `model_not_provisioned` rather than let a load
  download the model.
- For the no-fetch scenario, set `HF_ENDPOINT` and `MODELSCOPE_ENDPOINT` to a
  loopback blackhole in a `lemond.service` drop-in `Environment=` line.
  `systemctl show` exposes that line, so the scenario can verify it. Values in
  `EnvironmentFile=` are visible only when the runner can read the service's
  `/proc/<pid>/environ`, and the scenario reads only those two keys. Run the
  scenario with privileges that let it read the system journal, the service's
  model and backend caches, and the process owner of `lemond`'s sockets in
  `ss -p`.
- Pre-place the consumer models `user.zembed-1-Q4_K_M-GGUF-Q4_K_M` and
  `zerank-2-GGUF` (`mradermacher/zerank-2-GGUF:Q8_0`), and pin them in the
  service config. The consumer-pins scenario only reads them.
- For the pinned-chat scenario, pre-place and pin the host's qwen35moe chat
  model, and name it with `LEMONADE_PINNED_CHAT_MODEL` when it is not the
  default id.
- When the host's service configuration carries an API key, set `LEMONADE_API_KEY` or
  `LEMONADE_API_KEY_FILE` in the runner's environment. For `/internal/*`, set
  `LEMONADE_ADMIN_API_KEY` or `LEMONADE_ADMIN_API_KEY_FILE`; if neither is
  set, the regular key is used. A `*_FILE` variable can name a systemd
  credential. Never put keys or credential paths in scenario files.
- The provenance scenario expects the service config to have `offline` and
  `no_fetch_executables` set to true. It also expects `llamacpp.rocm_bin` and
  `llamacpp.vulkan_bin` to be absolute paths owned by the packaged backends.

## Kokoro TTS Decision

The frozen Lemonade candidate (`nisavid/lemonade` fork main `3d5991033`) can
run Kokoro with a local backend directory and `no_fetch_executables`. However,
its `backend_versions.json` records no digest for the `lemonade-sdk/Kokoros`
runtime asset, so a pre-provisioned runtime cannot have its version and digest
recorded without a fork change. Kokoro TTS and the app's TTS interaction are
therefore deferred to generation C W2B (#113), and this catalog has no TTS
scenario.
