# Granite vLLM gate fixtures

The Granite corpus fixes three nonstreaming requests and their response
assertions for `ibm-granite/granite-3.1-1b-a400m-instruct` at revision
`0da7a48b0276d500ce5922fd2b33944091fc6c09`. It lives in
`inference/fixtures/granite-3.1-1b-a400m-instruct.json`.

The basic fixture requires literal `12`, without surrounding whitespace, for
7 + 5. The tool fixture requires one parsed
OpenAI `get_weather` call for Tokyo in Celsius; it never calls a weather service.
The structured fixture requires the JSON object
`{"topic":"ocean","answer":"blue"}` under its two-field schema. Each request
uses temperature zero, one choice, and an explicit system message so the native
template does not inject a changing date.

## CPU validation

`tools/granite_server_smoke.py` exposes two pure interfaces:

- `validate_granite_response(mode, response)` returns the validated assistant
  message or raises `RuntimeError`. The mode is `basic`, `tool`, or `structured`.
  It requires exactly one choice and the fixture's finish reason. Tool arguments
  must be a JSON string; structured content must be a JSON object with the
  selected fields and values. Duplicate JSON fields and non-JSON numbers fail.
  An explicit non-null response error or assistant refusal fails even when the
  selected answer is present. Absent or null optional error/refusal fields pass.
- `parse_selected_moe_backend(server_log)` returns the single consistent backend
  named by an affirmative vLLM unquantized-oracle selection message. Candidate
  lists alone and negative diagnostics do not qualify; missing evidence and
  conflicting selected names fail. Repeated consistent selections pass.
  No backend is forced.
  Qualifying records are complete bare messages or `INFO` records located at
  `unquantized.py:<line>`, with the pinned vLLM timestamp, relative source path,
  process-name/PID prefix, and ANSI color formatting accepted. Arbitrary bracket
  labels or diagnostic prefixes do not qualify. Each qualifying line consists
  entirely of one or more complete oracle records separated by horizontal
  whitespace. A diagnostic sentence prefix or suffix makes that line
  nonqualifying; other complete lines can still establish selection. Custom
  logging formats need an explicit adapter rather than an inferred selection.

The logger-format cases follow vLLM's pinned
[logger](https://github.com/vllm-project/vllm/blob/ced6857a/vllm/logger.py),
[formatter](https://github.com/vllm-project/vllm/blob/ced6857a/vllm/logging_utils/formatter.py),
and [process decorator](https://github.com/vllm-project/vllm/blob/ced6857a/vllm/utils/system_utils.py).

Run `pytest tests/test_granite_server_smoke.py -q` for constructed response and
log checks. These checks import no GPU or model libraries and run no server.
They do not establish live model output, selected kernels, or token accounting.

## Runtime join

The corpus contains no operating envelope: context/output budgets, batching,
memory fraction, startup/request timeouts, and fit/fault-stop inputs must come
from the reviewed method before helper and scenario integration can launch a
GPU lane. Granite has no completion-token minimum. E2B's 1,025-token gate does
not transfer to this model.

The live tool lane uses the pinned native template and vLLM's `granite` parser
with automatic tool choice. It checks the initial parsed call, not a tool-result
round trip. A round trip needs a separately reviewed template/serialization
contract. The oracle log establishes backend selection, not every executed
kernel or the absence of runtime fallback.

[The two vLLM gate lanes](https://github.com/nisavid/arch-strix-halo-pkgs/issues/179)
join the maintained fit/fault-stop method, normal Lemonade state, and serialized
resource window before provisioning or execution. Qualification also binds
[C's selected model closure](https://github.com/nisavid/arch-strix-halo-pkgs/issues/183)
and [W0's fixture and operating-bound freeze](https://github.com/nisavid/arch-strix-halo-pkgs/issues/107).
Retain the corpus digest, consumed method revision, immutable C subject, raw
requests/responses, server log, and actual stop/fault outcomes. A CPU fixture
pass is not a passing runtime gate.
