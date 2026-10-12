#!/usr/bin/env python3
"""Check that the installed vLLM carries each upstream backport.

One behavior check per backport patch of python-vllm-rocm-gfx1151. Each check
drives the installed package the way the fixed code path is driven in
service, with synthetic inputs, and fails when the fix is absent. Nothing
here reads vLLM's source text.

The checks need no GPU, no network, no model files and no pytest. Each runs
in its own Python process with vLLM's CPU platform selected, so one check
cannot hide or disturb another.

    python tools/vllm_backport_smoke.py            # all checks
    python tools/vllm_backport_smoke.py --only 0019
    python tools/vllm_backport_smoke.py --list

Prints one PASS or FAIL line per patch, then a JSON summary. Exits 0 when
every selected check passes and 1 otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib
import importlib.metadata
import io
import json
import os
import subprocess
import sys
import tempfile
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


RESULT_MARKER = "@@vllm-backport-smoke "
PIXTRAL_CHAIN = (
    "bee",
    "granite4_vision",
    "lightonocr",
    "llava",
    "llava_next",
    "llava_next_video",
    "llava_onevision",
    "mistral3",
    "phi4siglip",
    "pixtral",
    "rvl",
)


class CheckFailure(Exception):
    """The installed package does not show the fixed behavior."""


def _require(problems: list[str]) -> None:
    if problems:
        raise CheckFailure("; ".join(problems))


def _version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = []
    for part in version.split("."):
        digits = "".join(char for char in part if char.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


# --------------------------------------------------------------------- 0017
def check_pixtral_chain_imports() -> str:
    """Import the Pixtral-chain model modules and build Pixtral's rotary
    embedding for two image grids."""
    transformers_version = _version("transformers")
    failed = {}
    for name in PIXTRAL_CHAIN:
        try:
            importlib.import_module(f"vllm.model_executor.models.{name}")
        except Exception as exc:  # noqa: BLE001
            failed[name] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
    if failed:
        first = next(iter(failed))
        raise CheckFailure(
            f"{len(failed)} of {len(PIXTRAL_CHAIN)} Pixtral-chain modules do not "
            f"import on transformers {transformers_version} "
            f"({', '.join(sorted(failed))}); {first}: {failed[first]}"
        )

    import torch
    from transformers import PixtralVisionConfig
    from transformers.models.pixtral.modeling_pixtral import apply_rotary_pos_emb

    from vllm.model_executor.models import pixtral

    config = PixtralVisionConfig(
        hidden_size=64,
        intermediate_size=128,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_channels=3,
        image_size=64,
        patch_size=16,
    )
    device = torch.device("cpu")
    if hasattr(pixtral, "PixtralVisionRotaryEmbedding"):
        rotary = pixtral.PixtralVisionRotaryEmbedding(config).to(device)
    else:
        rotary = pixtral.PixtralRotaryEmbedding(config, device)
    generator = torch.Generator().manual_seed(1)
    # patch embeddings of a 3x2 and a 4x4 grid: (1, hidden, grid_h, grid_w)
    patch_embeds_list = [
        torch.randn(1, config.hidden_size, 3, 2, generator=generator),
        torch.randn(1, config.hidden_size, 4, 4, generator=generator),
    ]
    with torch.no_grad():
        patch_embeds = torch.cat(
            [p.flatten(2).permute(0, 2, 1) for p in patch_embeds_list], dim=1
        )
        position_ids = pixtral.position_ids_in_meshgrid(
            patch_embeds_list, max_width=config.image_size // config.patch_size
        )
        cos, sin = rotary(patch_embeds, position_ids)
        heads = config.num_attention_heads
        head_dim = config.hidden_size // heads
        tokens = patch_embeds.shape[1]
        q = torch.randn(1, heads, tokens, head_dim, generator=generator)
        k = torch.randn(1, heads, tokens, head_dim, generator=generator)
        q_rot, k_rot = apply_rotary_pos_emb(q, k, cos, sin, unsqueeze_dim=0)
    problems = []
    if tuple(cos.shape) != (tokens, head_dim) or tuple(sin.shape) != (tokens, head_dim):
        problems.append(f"rotary tables have shape {tuple(cos.shape)}, not {(tokens, head_dim)}")
    if not all(bool(torch.isfinite(t).all()) for t in (cos, sin, q_rot, k_rot)):
        problems.append("rotary output is not finite")
    if not bool((q_rot - q).abs().max() > 1e-3):
        problems.append("the rotation left the queries unchanged")
    _require(problems)

    detail = (
        f"{len(PIXTRAL_CHAIN)} modules import on transformers {transformers_version}; "
        f"{type(rotary).__name__} rotates {tokens} positions"
    )
    if _version_tuple(transformers_version) < (5, 17):
        detail += (
            " (not decisive: before transformers 5.17 the unpatched package "
            "imports these modules too)"
        )
    return detail


# --------------------------------------------------------------------- 0018
def check_minimax_m3_video_preprocess() -> str:
    """Run the MiniMax-M3 video processor on a synthetic clip, through its
    public call and through _preprocess without do_convert_rgb."""
    import torch
    from transformers.image_utils import SizeDict

    from vllm.transformers_utils.processors.minimax_m3 import MiniMaxM3VLVideoProcessor

    processor = MiniMaxM3VLVideoProcessor()
    generator = torch.Generator().manual_seed(0)
    # 4 frames, channels first, 112x168 pixels
    clip = torch.randint(0, 256, (4, 3, 112, 168), dtype=torch.uint8, generator=generator)

    size = processor.size
    if not isinstance(size, SizeDict):
        size = SizeDict(**size)
    try:
        direct = processor._preprocess(
            videos=[clip],
            do_resize=processor.do_resize,
            size=size,
            resample=processor.resample,
            do_rescale=processor.do_rescale,
            rescale_factor=processor.rescale_factor,
            do_normalize=processor.do_normalize,
            image_mean=processor.image_mean,
            image_std=processor.image_std,
            patch_size=processor.patch_size,
            temporal_patch_size=processor.temporal_patch_size,
            merge_size=processor.merge_size,
            min_pixels=processor.min_pixels,
            max_pixels=processor.max_pixels,
            return_tensors="pt",
        )
    except TypeError as exc:
        if "do_convert_rgb" not in str(exc):
            raise
        raise CheckFailure(f"_preprocess without do_convert_rgb: {exc}") from exc
    try:
        public = processor(videos=[clip], return_tensors="pt")
    except TypeError as exc:
        if "do_convert_rgb" not in str(exc):
            raise
        raise CheckFailure(
            f"the processor call fails on transformers {_version('transformers')}: {exc}"
        ) from exc

    problems = []
    for name, output in (("_preprocess", direct), ("call", public)):
        patches = output["pixel_values_videos"]
        grid = output["video_grid_thw"]
        if patches.ndim != 2 or patches.shape[0] == 0 or tuple(grid.shape) != (1, 3):
            problems.append(
                f"{name} returned patches {tuple(patches.shape)} and grid {tuple(grid.shape)}"
            )
        elif int(grid.prod()) != patches.shape[0]:
            problems.append(f"{name}: grid {grid.tolist()} does not match {patches.shape[0]} patches")
    _require(problems)
    return (
        f"_preprocess and the processor call both return "
        f"{tuple(public['pixel_values_videos'].shape)} patches on transformers "
        f"{_version('transformers')}"
    )


# --------------------------------------------------------------------- 0019
class _StubHFConfig:
    model_type = "any"


class _StubModelConfig:
    """What OnlineRenderer reads from a model config before it renders."""

    task = "generate"
    runner_type = "generate"
    model = "stub-model"
    tokenizer = "stub-model"
    trust_remote_code = False
    tokenizer_mode = "auto"
    max_model_len = 100
    tokenizer_revision = None
    hf_config = _StubHFConfig()
    hf_text_config = _StubHFConfig()
    logits_processors = None
    diff_sampling_param = None
    allowed_local_media_path = ""
    allowed_media_domains = None
    encoder_config = None
    generation_config = "auto"
    skip_tokenizer_init = False
    is_encoder_decoder = False
    is_multimodal_model = False
    renderer_num_workers = 1
    enable_prompt_embeds = False

    def __init__(self) -> None:
        from vllm.config.multimodal import MultiModalConfig

        self.multimodal_config = MultiModalConfig()
        self.media_io_kwargs: dict = {}

    def get_diff_sampling_param(self) -> dict:
        return {}


async def _send_chat(online_renderer, model_renderer, request) -> dict:
    """Send one request through OnlineRenderer.preprocess_chat, the entry the
    chat, Responses, tokenize and batch routes share."""
    from vllm.entrypoints.serve.exception_handling.error_response import (
        create_error_response,
    )
    from vllm.exceptions import VLLMValidationError

    model_renderer.render_chat_async.reset_mock()
    outcome: dict = {"rejected": False}
    try:
        await online_renderer.preprocess_chat(
            request,
            request.messages,
            default_template=None,
            default_template_content_format="auto",
            default_template_kwargs=None,
        )
    except VLLMValidationError as exc:
        outcome["rejected"] = True
        outcome["message"] = str(exc)
        outcome["http_status"] = int(create_error_response(exc).error.code)
    except Exception as exc:  # noqa: BLE001
        # Past the gate, the mocked model renderer's output is not a real prompt.
        outcome["after_gate"] = f"{type(exc).__name__}: {exc}"
    outcome["reached_model_renderer"] = bool(model_renderer.render_chat_async.await_args_list)
    return outcome


async def _send_score(trust: bool | None) -> dict:
    """Send a score request through ServingScores.flash_late_interaction,
    which enters PoolingBaseServing._init_ctx like every pooling route."""
    from unittest.mock import MagicMock

    from vllm.config.multimodal import MultiModalConfig
    from vllm.entrypoints.pooling.base.serving import PoolingBaseServing
    from vllm.entrypoints.pooling.scoring.protocol import ScoreQueriesDocumentsRequest
    from vllm.entrypoints.pooling.scoring.serving import ServingScores
    from vllm.exceptions import VLLMValidationError

    serving = MagicMock()
    serving.model_config = MagicMock(multimodal_config=MultiModalConfig())
    if trust is not None:
        serving.trust_request_mm_kwargs = trust
    serving.io_processor = MagicMock()
    serving._init_ctx = PoolingBaseServing._init_ctx.__get__(serving)
    request = ScoreQueriesDocumentsRequest(
        model="stub-model",
        queries="What is the capital of France?",
        documents="The capital of France is Paris.",
        mm_processor_kwargs={"vision_min_num_patches": 3_000_000_000},
    )
    outcome: dict = {"rejected": False}
    try:
        await ServingScores.flash_late_interaction(serving, request)
    except VLLMValidationError as exc:
        outcome["rejected"] = "Per-request mm_processor_kwargs are disabled" in str(exc)
        outcome["message"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        # Past the gate, the mocked serving object is not awaitable.
        outcome["after_gate"] = f"{type(exc).__name__}: {exc}"
    outcome["preprocessing_called"] = bool(serving._preprocessing.called)
    return outcome


def check_per_request_mm_kwargs_gate() -> str:
    """Send chat, tokenize and score requests that carry per-request
    multimodal kwargs to a default server and to one that trusts them."""
    import inspect
    from unittest.mock import AsyncMock, MagicMock

    from vllm.entrypoints.launchers.cli_args import FrontendArgs
    from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest
    from vllm.entrypoints.serve.tokenize.protocol import TokenizeChatRequest
    from vllm.renderers.online_renderer import OnlineRenderer
    from vllm.utils.argparse_utils import FlexibleArgumentParser

    messages = [{"role": "user", "content": "hello"}]
    oversized = {"vision_min_num_patches": 3_000_000_000}
    requests = {
        "chat with mm_processor_kwargs": ChatCompletionRequest(
            model="stub-model", messages=messages, mm_processor_kwargs=oversized
        ),
        "chat with media_io_kwargs": ChatCompletionRequest(
            model="stub-model",
            messages=messages,
            media_io_kwargs={"video": {"num_frames": 1_000_000}},
        ),
        "tokenize with mm_processor_kwargs": TokenizeChatRequest(
            model="stub-model", messages=messages, mm_processor_kwargs=oversized
        ),
    }
    plain = ChatCompletionRequest(model="stub-model", messages=messages)

    def online_renderer(**kwargs):
        model_renderer = MagicMock()
        model_renderer.render_chat_async = AsyncMock(
            return_value=([[]], [{"type": "tokens", "prompt_token_ids": [1]}])
        )
        renderer = OnlineRenderer(
            model_config=_StubModelConfig(),
            renderer=model_renderer,
            request_logger=None,
            chat_template=None,
            chat_template_content_format="auto",
            **kwargs,
        )
        return renderer, model_renderer

    problems = []

    # A server started without the flag.
    renderer, model_renderer = online_renderer()
    for name, request in requests.items():
        outcome = asyncio.run(_send_chat(renderer, model_renderer, request))
        if not outcome["rejected"]:
            reached = "and reached the model renderer" if outcome["reached_model_renderer"] else ""
            problems.append(f"default server: {name} was not rejected {reached}".rstrip())
        elif outcome["http_status"] != 400 or outcome["reached_model_renderer"]:
            problems.append(f"default server: {name} was rejected with {outcome}")
    outcome = asyncio.run(_send_chat(renderer, model_renderer, plain))
    if outcome["rejected"] or not outcome["reached_model_renderer"]:
        problems.append(f"default server: a plain chat request did not render: {outcome}")
    score = asyncio.run(_send_score(False))
    if not score["rejected"] or score["preprocessing_called"]:
        problems.append("default server: score with mm_processor_kwargs was not rejected")

    # The opt-in: the CLI flag, then a server that trusts request kwargs.
    parser = FrontendArgs.add_cli_args(FlexibleArgumentParser())
    trusted_flag = None
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            default_flag = getattr(parser.parse_args([]), "trust_request_mm_kwargs", None)
            trusted_flag = parser.parse_args(["--trust-request-mm-kwargs"]).trust_request_mm_kwargs
        except SystemExit:
            default_flag = None
    if default_flag is not False or trusted_flag is not True:
        problems.append("the server CLI does not know --trust-request-mm-kwargs")
    if "trust_request_mm_kwargs" not in inspect.signature(OnlineRenderer.__init__).parameters:
        problems.append("the renderer has no trust_request_mm_kwargs option")
    else:
        renderer, model_renderer = online_renderer(trust_request_mm_kwargs=True)
        for name, request in requests.items():
            outcome = asyncio.run(_send_chat(renderer, model_renderer, request))
            if outcome["rejected"] or not outcome["reached_model_renderer"]:
                problems.append(f"trusting server: {name} did not render: {outcome}")
        score = asyncio.run(_send_score(True))
        if score["rejected"]:
            problems.append("trusting server: score with mm_processor_kwargs was rejected")
    _require(problems)
    return (
        "chat, tokenize and score requests with per-request multimodal kwargs get "
        "a validation error (HTTP 400) by default and render with "
        "--trust-request-mm-kwargs"
    )


# --------------------------------------------------------------------- 0020
def check_error_message_redaction() -> str:
    """Sanitize error messages that hold upper-case object addresses."""
    from PIL import Image

    from vllm.entrypoints.serve.exception_handling.utils import sanitize_message

    literal = "<PIL.Image.Image image mode=RGB size=2x2 at 0x7D52EAF07BF0>"
    live = repr(Image.new("RGB", (2, 2)))
    problems = []
    if sanitize_message(literal) != "<PIL.Image.Image image mode=RGB size=2x2>":
        problems.append(f"an upper-case address survives: {sanitize_message(literal)!r}")
    if " at 0x" in sanitize_message(f"cannot process {live}"):
        problems.append(f"a live PIL repr keeps its address: {sanitize_message(live)!r}")
    if sanitize_message("<_io.BytesIO object at 0x7a95e299e750>") != "<_io.BytesIO object>":
        problems.append("a lower-case address is no longer redacted")
    _require(problems)
    return "upper-case and lower-case object addresses are stripped from error messages"


# --------------------------------------------------------------------- 0021
def check_receiver_cache_prefers_resent_payload() -> str:
    """Resend a different item under one identity to the engine-side
    multimodal cache."""
    from vllm.config.multimodal import MultiModalConfig
    from vllm.multimodal.cache import MultiModalReceiverCache
    from vllm.multimodal.inputs import (
        MultiModalFeatureSpec,
        MultiModalKwargsItem,
        PlaceholderRange,
    )

    class StubModelConfig:
        def get_multimodal_config(self) -> MultiModalConfig:
            return MultiModalConfig(mm_processor_cache_gb=1)

    identity = "shared-id"
    stale = MultiModalKwargsItem.dummy(nbytes=64)
    resent = MultiModalKwargsItem.dummy(nbytes=256)
    problems = []

    cache = MultiModalReceiverCache(StubModelConfig())
    if cache.get_and_update_item(stale, identity) is not stale:
        problems.append("the first payload was not returned")
    if cache.get_and_update_item(resent, identity) is not resent:
        problems.append("a resent payload was replaced by the stale cached item")
    if cache.get_and_update_item(None, identity) is not resent:
        problems.append("a later cache hit does not return the resent payload")

    def feature(data, length: int) -> MultiModalFeatureSpec:
        return MultiModalFeatureSpec(
            data=data,
            modality="image",
            identifier=identity,
            mm_position=PlaceholderRange(offset=0, length=length),
            mm_hash=identity,
        )

    cache = MultiModalReceiverCache(StubModelConfig())
    cache.get_and_update_features([feature(stale, 4)])
    updated = cache.get_and_update_features([feature(resent, 2048)])
    if updated[0].data is not resent:
        problems.append(
            "a request with 2048 placeholders was paired with the stale cached item"
        )
    _require(problems)
    return "a resent payload replaces the stale receiver-cache entry and serves later hits"


# --------------------------------------------------------------------- 0022
def check_encoder_cache_embed_count_mismatch() -> str:
    """Schedule a request whose multimodal identifier matches an encoder
    cache entry that holds a different number of embeddings."""
    import types

    import torch

    from vllm.multimodal.inputs import MultiModalFeatureSpec, PlaceholderRange
    from vllm.v1.core.encoder_cache_manager import EncoderCacheManager
    from vllm.v1.core.sched.scheduler import Scheduler

    class StubRequest:
        has_encoder_inputs = True

        def __init__(self, request_id: str, identifier: str, is_embed: list[bool]) -> None:
            self.request_id = request_id
            self.mm_features = [
                MultiModalFeatureSpec(
                    data=None,
                    modality="image",
                    identifier=identifier,
                    mm_position=PlaceholderRange(
                        offset=0, length=len(is_embed), is_embed=torch.tensor(is_embed)
                    ),
                )
            ]

        def get_num_encoder_embeds(self, input_id: int) -> int:
            return self.mm_features[input_id].mm_position.get_num_embeds()

    def schedule(request: StubRequest, manager: EncoderCacheManager):
        """Call the scheduler's encoder-input step on a minimal scheduler."""
        scheduler = types.SimpleNamespace(
            is_encoder_decoder=False,
            ec_connector=None,
            encoder_cache_manager=manager,
            encoder_cache_mismatch_reqs=set(),
            scheduler_config=types.SimpleNamespace(disable_chunked_mm_input=False),
        )
        reject = getattr(Scheduler, "_reject_on_encoder_cache_embed_mismatch", None)
        if reject is not None:
            scheduler._reject_on_encoder_cache_embed_mismatch = types.MethodType(
                reject, scheduler
            )
        tokens = request.mm_features[0].mm_position.length
        result = Scheduler._try_schedule_encoder_inputs(
            scheduler,
            request,
            num_computed_tokens=0,
            num_new_tokens=tokens,
            encoder_compute_budget=1024,
        )
        return result, scheduler.encoder_cache_mismatch_reqs

    identifier = "client-reused-uuid"

    def cache_with_freed_entry() -> EncoderCacheManager:
        manager = EncoderCacheManager(cache_size=64)
        owner = StubRequest("owner", identifier, [True, True, True, False, False, False])
        manager.allocate(owner, 0)
        manager.free(owner)
        return manager

    problems = []
    logging_was_disabled = _silence_vllm_logging()
    try:
        # Same identifier, same 3 embeddings: an ordinary cache hit.
        matching = StubRequest("matching", identifier, [True, False, True, False, True, False, False])
        (to_encode, new_tokens, _, _), mismatched = schedule(matching, cache_with_freed_entry())
        if to_encode or new_tokens != 7 or mismatched:
            problems.append(
                f"a matching cache hit was not reused: encode={to_encode}, tokens={new_tokens}"
            )
        # Same identifier, 4 embeddings against the cached 3.
        request = StubRequest("mismatched", identifier, [True, True, True, True, False, False])
        (to_encode, new_tokens, _, _), mismatched = schedule(request, cache_with_freed_entry())
        if new_tokens != 0 or "mismatched" not in mismatched:
            problems.append(
                "a request expecting 4 embeddings was scheduled against a cache entry "
                f"holding 3 (tokens scheduled: {new_tokens})"
            )
    finally:
        _restore_vllm_logging(logging_was_disabled)
    _require(problems)
    return (
        "an encoder-cache hit with a different embedding count fails the request; "
        "a matching hit is reused"
    )


def _silence_vllm_logging() -> bool:
    import logging

    logger = logging.getLogger("vllm")
    was_disabled = logger.disabled
    logger.disabled = True
    return was_disabled


def _restore_vllm_logging(was_disabled: bool) -> None:
    import logging

    logging.getLogger("vllm").disabled = was_disabled


# --------------------------------------------------------------------- 0023
def check_multimodal_hash_framing() -> str:
    """Hash pairs of distinct processor kwargs that serialize to the same
    unframed digest input."""
    from vllm.multimodal.hasher import MultiModalHasher

    image = b"\x89PNG\r\n\x1a\n"

    def digest(**mm_processor_kwargs: object) -> str:
        return MultiModalHasher.hash_kwargs(
            "sha256", model_id="m", image=image, **mm_processor_kwargs
        )

    pairs = {
        "key/value boundary": ({"ab": "c"}, {"a": "bc"}),
        "nested mapping vs dotted key": (
            {"size": {"shortest_edge": 224}},
            {"size.shortest_edge": 224},
        ),
        "sequence vs index-keyed mapping": ({"fps": [2, 4]}, {"fps": {"0": 2, "1": 4}}),
        "None vs empty string": ({"video_pruning_rate": None}, {"video_pruning_rate": ""}),
        "empty mapping vs omitted key": ({"size": {}}, {}),
        "empty sequence vs omitted key": ({"size": []}, {}),
    }
    collisions = [
        name for name, (left, right) in pairs.items() if digest(**left) == digest(**right)
    ]
    if collisions:
        raise CheckFailure(
            f"{len(collisions)} of {len(pairs)} distinct inputs share a hash: "
            + ", ".join(collisions)
        )
    if digest(fps=[2, 4]) != digest(fps=[2, 4]):
        raise CheckFailure("the hash is not deterministic")
    return f"{len(pairs)} input pairs that collide under the unframed digest hash differently"


# --------------------------------------------------------------------- 0024
def check_incremental_block_hashing() -> str:
    """Extend a request's block hashes after generation, with two multimodal
    inputs in the new block, and compare with hashing in one pass."""
    from vllm.multimodal.inputs import (
        MultiModalFeatureSpec,
        MultiModalKwargsItem,
        PlaceholderRange,
    )
    from vllm.sampling_params import SamplingParams
    from vllm.utils.hashing import sha256
    from vllm.v1.core.kv_cache_utils import get_request_block_hasher, init_none_hash
    from vllm.v1.request import Request

    init_none_hash(sha256)
    positions = [PlaceholderRange(offset=4, length=2), PlaceholderRange(offset=6, length=1)]

    def make_request(request_id: str, prompt_token_ids: list[int]) -> Request:
        sampling_params = SamplingParams(max_tokens=17)
        sampling_params.update_from_generation_config({}, eos_token_id=100)
        return Request(
            request_id=request_id,
            prompt_token_ids=prompt_token_ids,
            mm_features=[
                MultiModalFeatureSpec(
                    data=MultiModalKwargsItem.dummy(),
                    mm_position=position,
                    identifier=identifier,
                    modality="image",
                )
                for position, identifier in zip(positions, ("A", "B"), strict=True)
            ],
            sampling_params=sampling_params,
            pooling_params=None,
            lora_request=None,
            cache_salt=None,
            block_hasher=get_request_block_hasher(4, sha256),
        )

    incremental = make_request("incremental", list(range(7)))
    incremental.append_output_token_ids(7)
    fresh = make_request("fresh", list(range(8)))
    if len(fresh.block_hashes) != 2 or len(incremental.block_hashes) != 2:
        raise CheckFailure(
            f"expected two full blocks, got {len(incremental.block_hashes)} "
            f"incremental and {len(fresh.block_hashes)} in one pass"
        )
    if incremental.block_hashes[0] != fresh.block_hashes[0]:
        raise CheckFailure("the first block already hashes differently")
    if incremental.block_hashes[1] != fresh.block_hashes[1]:
        raise CheckFailure(
            "a block holding two multimodal inputs hashes differently when it is "
            "completed during generation than when it is hashed in one pass"
        )
    return "incremental and one-pass hashes match for a block with two multimodal inputs"


# ------------------------------------------------------------------ registry
@dataclass(frozen=True)
class Check:
    patch: str
    summary: str
    run: Callable[[], str]

    @property
    def number(self) -> str:
        return self.patch.split("-", 1)[0]


CHECKS = (
    Check(
        "0017-backport-pixtral-axial-rope-for-transformers-5.17.patch",
        "Pixtral-chain model modules import and Pixtral's rotary embedding runs",
        check_pixtral_chain_imports,
    ),
    Check(
        "0018-backport-minimax-m3-video-processor-for-transformers-5.18.patch",
        "MiniMax-M3 video processor runs without do_convert_rgb",
        check_minimax_m3_video_preprocess,
    ),
    Check(
        "0019-backport-gate-per-request-multimodal-kwargs.patch",
        "per-request multimodal kwargs are rejected unless the server trusts them",
        check_per_request_mm_kwargs_gate,
    ),
    Check(
        "0020-backport-redact-upper-case-addresses-in-error-messages.patch",
        "upper-case object addresses are redacted from error messages",
        check_error_message_redaction,
    ),
    Check(
        "0021-backport-prefer-fresh-multimodal-payloads-over-stale-receiver-cache.patch",
        "a resent payload replaces a stale receiver-cache entry",
        check_receiver_cache_prefers_resent_payload,
    ),
    Check(
        "0022-backport-reject-encoder-cache-hits-with-mismatched-embed-counts.patch",
        "an encoder-cache hit with a mismatched embedding count is rejected",
        check_encoder_cache_embed_count_mismatch,
    ),
    Check(
        "0023-backport-frame-the-multimodal-hash-digest-input.patch",
        "distinct multimodal inputs hash differently",
        check_multimodal_hash_framing,
    ),
    Check(
        "0024-backport-fix-incremental-multimodal-block-hashing.patch",
        "incremental block hashing matches one-pass hashing",
        check_incremental_block_hashing,
    ),
)


def select_checks(only: list[str]) -> list[Check]:
    """Checks whose patch number or patch file name is in ``only`` (all when
    empty), in registry order."""
    if not only:
        return list(CHECKS)
    known = {check.number for check in CHECKS} | {check.patch for check in CHECKS}
    unknown = [name for name in only if name not in known]
    if unknown:
        raise ValueError(f"no check for: {', '.join(unknown)}")
    return [check for check in CHECKS if check.number in only or check.patch in only]


def run_check(check: Check) -> dict:
    """Run one check in this process. Never raises."""
    record = {"patch": check.patch, "number": check.number, "summary": check.summary}
    try:
        record.update(ok=True, detail=check.run())
    except CheckFailure as exc:
        record.update(ok=False, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        frames = traceback.extract_tb(exc.__traceback__)
        where = f" at {Path(frames[-1].filename).name}:{frames[-1].lineno}" if frames else ""
        message = str(exc).strip().splitlines()[0][:300] if str(exc).strip() else ""
        record.update(ok=False, detail=f"{type(exc).__name__}: {message}{where}")
    return record


def child_environment(scratch: str) -> dict[str, str]:
    """The environment for one check: vLLM's CPU platform, no GPU, no network,
    and every cache under a throwaway directory."""
    env = dict(os.environ)
    env.update(
        VLLM_TARGET_DEVICE="cpu",
        CUDA_VISIBLE_DEVICES="",
        HIP_VISIBLE_DEVICES="",
        ROCR_VISIBLE_DEVICES="",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        VLLM_NO_USAGE_STATS="1",
        DO_NOT_TRACK="1",
        TOKENIZERS_PARALLELISM="false",
        PYTHONDONTWRITEBYTECODE="1",
    )
    for variable, name in (
        ("HOME", "home"),
        ("XDG_CACHE_HOME", "xdg-cache"),
        ("XDG_CONFIG_HOME", "xdg-config"),
        ("HF_HOME", "hf"),
        ("VLLM_CACHE_ROOT", "vllm-cache"),
        ("VLLM_CONFIG_ROOT", "vllm-config"),
        ("TRITON_CACHE_DIR", "triton"),
        ("TORCHINDUCTOR_CACHE_DIR", "inductor"),
    ):
        path = Path(scratch) / name
        path.mkdir(parents=True, exist_ok=True)
        env[variable] = str(path)
    return env


def run_check_in_child(check: Check, scratch: str, timeout: float) -> dict:
    """Run one check in a fresh interpreter and return its record."""
    record = {"patch": check.patch, "number": check.number, "summary": check.summary}
    try:
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--child", check.patch],
            env=child_environment(scratch),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        record.update(ok=False, detail=f"timed out after {timeout:.0f}s")
        return record
    tail = (proc.stderr.strip().splitlines() or ["no output"])[-1][:300]
    for line in proc.stdout.splitlines():
        if line.startswith(RESULT_MARKER):
            reported = json.loads(line[len(RESULT_MARKER) :])
            if proc.returncode == 0:
                return reported
            # A crash after the record (at shutdown, say) must not pass.
            reported.update(
                ok=False,
                detail=f"the check reported {reported['detail']!r}, "
                f"but its process exited {proc.returncode}: {tail}",
            )
            return reported
    record.update(ok=False, detail=f"the check process exited {proc.returncode}: {tail}")
    return record


def installed_versions() -> dict[str, str]:
    return {
        name: _version(name)
        for name in ("vllm", "transformers", "huggingface_hub", "torch")
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check that the installed vLLM carries each upstream backport "
            "(CPU only, offline)."
        )
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="PATCH",
        help="run only this patch's check, by number (0019) or file name; repeatable",
    )
    parser.add_argument("--list", action="store_true", help="list the checks and exit")
    parser.add_argument(
        "--json", metavar="PATH", help="also write the JSON summary to this file"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="seconds allowed per check (default: 600)",
    )
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="run the checks in this process instead of one process each",
    )
    parser.add_argument("--child", metavar="PATCH", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.child:
        (check,) = select_checks([args.child])
        print(RESULT_MARKER + json.dumps(run_check(check)), flush=True)
        return 0
    if args.timeout <= 0:
        print("vllm_backport_smoke: --timeout must be positive", file=sys.stderr)
        return 2
    try:
        checks = select_checks(args.only)
    except ValueError as exc:
        print(f"vllm_backport_smoke: {exc}", file=sys.stderr)
        return 2
    if args.list:
        for check in checks:
            print(f"{check.number} {check.patch}: {check.summary}")
        return 0

    results = []
    with tempfile.TemporaryDirectory(prefix="vllm-backport-smoke-") as scratch:
        for check in checks:
            if args.in_process:
                record = run_check(check)
            else:
                record = run_check_in_child(check, scratch, args.timeout)
            results.append(record)
            status = "PASS" if record["ok"] else "FAIL"
            print(f"{status} {record['number']} {record['patch']}: {record['detail']}", flush=True)

    summary = {
        "tool": "vllm_backport_smoke",
        "versions": installed_versions(),
        "passed": [record["number"] for record in results if record["ok"]],
        "failed": [record["number"] for record in results if not record["ok"]],
        "results": results,
    }
    text = json.dumps(summary, indent=2)
    print(text)
    if args.json:
        Path(args.json).write_text(text + "\n")
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
