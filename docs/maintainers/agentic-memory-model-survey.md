# Models for broad, large agentic memory stores

This survey recommends candidates in four tiers for embedding, reranking, fact
extraction, consolidation, and answer synthesis across engineering, sciences,
humanities, law, and personal matters. It prioritizes fast recall, reasonably
fast retention, and useful retrieval as stores grow to tens or hundreds of
thousands of memories. It compares public evidence available on
2026-10-01; it does not select a production model or establish performance on
Strix Halo or on a particular memory store.

The retained zembed-1 and zerank-2 fixtures remain approved for noncommercial
validation. These candidates are supplements, not replacements for those
fixtures or generation C's existing role contracts. The decisions are recorded
on [#107](https://github.com/nisavid/arch-strix-halo-pkgs/issues/107#issuecomment-5926261155).
Approval covers noncommercial validation use, not static or runtime admission.
#107 remains incomplete; this survey does not admit selectors, unblock generation
C, or change the managed Kokoro admission-proof requirements. No weights were
downloaded, inference run, data indexed, or models deployed in this survey.
Custom datasets and evaluations are future work.

## Recommended starting candidates

Each entry below is my recommended contender for its tier, not a proved winner.
“Local” means downloadable models eligible for commercial use under their stated
terms; it does not establish Strix Halo serving compatibility. “Tiny” means a
useful local automated-testing fixture. For generative slots, the model must
produce coherent, meaningful memory behavior; an embedding or reranking fixture
instead needs meaningful semantic ordering. Parameter count alone settles neither.
One entrant can satisfy several tiers.

| Memory role | Best local tiny for testing | Best local contender | Best inexpensive contender | Best-of-all contender |
| --- | --- | --- | --- | --- |
| Embedding: retrieve semantic candidates | **Granite97M Multilingual R2**; escalate to Granite311M or Qwen0.6B if semantic acceptance fails | **Nemotron-3-Embed-8B**; compare Harrier27B and Qwen8B | **Hosted pplx-embed-0.6b**, $0.004/M input tokens | **Cohere Embed5 Pro**, with Voyage4-large as the mandatory text-retrieval comparison |
| Reranking: order retrieved candidates | **Ettin68M** for English; **Qwen3-Reranker-0.6B** for multilingual tests | **Qwen3-Reranker-4B** for broad quality; compare 8B and use Ettin150M as the English speed challenger | **Voyage rerank-3-lite**, $0.02/M processed tokens | **Voyage rerank-3**, with Cohere Rerank4 Pro and commercially licensed Jina3.5 as challengers |
| Retain: extract structured, temporally grounded facts | **Qwen3.5-4B**, with the required MTP main/draft route | **Qwen3.6-35B-A3B**, compared with GPT-OSS-20B at low reasoning effort | **GPT-OSS-20B on Groq**, $0.075/$0.30 per M input/output tokens; GPT-6 Luna is the newer alternative | **GPT-6 Astra**, compared with Claude Fable5.1 |
| Consolidate: merge evidence while preserving conflicts and historical state | **Qwen3.5-4B**, same coherence floor | **Qwen3.6-27B**; compare 35B-A3B for throughput | **GPT-OSS-20B on Groq**, with GPT-6 Luna as an alternative | **GPT-6 Astra**, compared with Claude Fable5.1 |
| Synthesize / reflect: answer from retrieved evidence, use tools, and abstain | **Qwen3.5-4B**, same coherence floor | **Qwen3.6-27B**; GPT-OSS-120B is the larger direct-memory-evidence contender if feasible | **GPT-OSS-20B on Groq**, with GPT-6 Luna as an alternative | **GPT-6 Astra**, compared with Claude Fable5.1 and Gemini3.8 Flash |

The quality-ceiling generative choices are inferred from current publisher
capabilities and general reasoning evidence. No inspected broad-memory comparison
settles their order. Consolidation has especially weak direct comparative
evidence. The embedding ceiling is also provisional: Cohere's new parsed-document
results and Voyage's text-retrieval results use different evaluation methods.
The sections below supply sources and conditions for these judgments.

The retained Qwen3-0.6B-Q8_0 Lemonade basic smoke fixture and Qwen3.5-4B MTP
main/draft role remain separate requirements. Main/draft qualification still
blocks generation C. The operator recalls choosing the 4B model because smaller
generative models were not reliably coherent; that is prior operator experience,
not a result reproduced here. Neither the basic smoke pass nor this research
qualifies extraction, consolidation, or MTP serving.

## What the shortlist needs to solve

An embedding model supplies semantic candidates; a reranker scores a bounded
candidate set. Neither establishes that extraction preserved the relevant fact,
that the search index returned it, or that a historical fact still applies.
Hindsight's current architecture combines semantic, keyword, entity, and
temporal retrieval before fusion and reranking. Its retention path includes
extraction, entity resolution, temporal grounding, embedding, and database work;
observation consolidation adds background model work.
[Recall](https://hindsight.vectorize.io/developer/retrieval),
[retain](https://hindsight.vectorize.io/developer/retain), and
[observations](https://hindsight.vectorize.io/developer/observations).

For a large mixed store, I would compare the models within a retrieval system
that preserves lexical and entity matches alongside semantic matches. Exact
symbols, rare names, case citations, units, negations, and dates are practical
reasons for that recommendation. A larger reranker cannot rescue an omitted
candidate. Reasoning or query reformulation can help difficult searches, but
adds latency; it should be compared separately from everyday recall.
[BRIGHT](https://arxiv.org/abs/2407.12883v4) provides reasoning-intensive retrieval
evidence across mathematics, coding, psychology, and economics rather than
ordinary similarity matching alone.

## Embedding candidates

Licenses in this table are publisher declarations inspected through model cards
and Hugging Face metadata on the survey date. Apache-2.0 and MIT candidates are
commercially usable subject to their terms. Gemma uses its own terms. Converted
artifacts and serving code need their own provenance and license review before
admission. Dimensions and context are model specifications, not measured local
limits or quality guarantees.

| Candidate | Published size, vector dimensions, and input limit | License | Why I would consider it; material tradeoff |
| --- | --- | --- | --- |
| [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | 0.6B; 1024 dimensions with Matryoshka reduction; 32K tokens | Apache-2.0 | Balanced multilingual and code retrieval candidate with query instructions, last-token pooling, and normalization. [Official GGUF](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF) makes its llama.cpp path particularly concrete. |
| [pplx-embed-v1-0.6b](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b) | 0.6B; 1024 dimensions with reduction; 32K | MIT | Strong challenger with bidirectional attention, mean pooling, no instruction prefixes, and native int8/binary outputs. Its vectors are unnormalized; the scorer must honor the published similarity contract. Contextual variants require a different indexing contract. |
| [Granite-Embedding-97M-Multilingual-R2](https://huggingface.co/ibm-granite/granite-embedding-97m-multilingual-r2) | 97M; 384 dimensions; 32K | Apache-2.0 | Compact multilingual encoder with CLS pooling and no retrieval prefix in the examples. Retrieval training explicitly covers 52 languages and code; the broader pretraining-language count should not be advertised as equivalent retrieval coverage. |
| [EmbeddingGemma-300M](https://huggingface.co/google/embeddinggemma-300m) | About 300M; 768/512/256/128 dimensions; 2048 tokens | [Gemma terms](https://ai.google.dev/gemma/docs/embeddinggemma) | Compact multilingual alternative for short memories. Mean pooling, learned projections, and query/document formatting must survive conversion. Its short input limit is a real tradeoff for long source passages. |
| [Nemotron-3-Embed-8B-BF16](https://huggingface.co/nvidia/Nemotron-3-Embed-8B-BF16) | 8B; 4096 dimensions, reducible by slicing and renormalizing; 32,768 tokens | [OpenMDW-1.1](https://openmdw.ai/license/1-1/) | Current retrieval-quality contender with bidirectional attention, average pooling, query/passage prefixes, and normalization. Its publisher validation uses NVIDIA hardware; ROCm/GGUF serving remains unqualified. |
| [Qwen3-Embedding-4B](https://huggingface.co/Qwen/Qwen3-Embedding-4B), [8B](https://huggingface.co/Qwen/Qwen3-Embedding-8B) | 4B/8B; 2560/4096 dimensions with reduction; 32K | Apache-2.0 | Larger quality comparators for multilingual, code, and difficult semantic retrieval. Extra encoding cost affects both query latency and retention throughput; larger vectors also affect index cost. |
| [pplx-embed-v1-4b](https://huggingface.co/perplexity-ai/pplx-embed-v1-4b) | 4B; 2560 dimensions with reduction; 32K | MIT | Quality comparator against Qwen4B with native compressed-vector options. The publisher's scale experiments are useful evidence, but involve private web/query corpora rather than agent memories. |
| [Voyage-4-nano](https://huggingface.co/voyageai/voyage-4-nano) | About 340M total parameters; 2048/1024/512/256 dimensions; nominal 32,000 tokens | Apache-2.0 | Compact code-retrieval challenger and an unusual shared embedding-space option with hosted Voyage4 models. Mean pooling, bidirectional architecture, and query/document prompts are part of its contract. |
| [Granite311M R2](https://huggingface.co/ibm-granite/granite-embedding-311m-multilingual-r2) | 311M; 768 dimensions, reducible to 128; 32K | Apache-2.0 | Compact long-input challenger between the 97M and decoder-sized candidates. It supplies retrieval, code, long-input, and reasoning benchmark slices, rather than only an aggregate score. |
| [Harrier OSS v1](https://huggingface.co/microsoft/harrier-oss-v1-270m) | 270M/0.6B/27B; 640/1024/5376 dimensions; 32K | MIT | Newer multilingual challenger with query instructions and last-token pooling. The 270M/0.6B variants deserve attention; 27B is costly for routine recall. No dimension-reduction contract was established in the inspected cards. |
| [LightOn mDenseOn](https://huggingface.co/lightonai/mDenseOn) | 307M; 768 dimensions; 8K | Apache-2.0 | Retrieval-focused multilingual encoder with CLS pooling and query/document prefixes. Its target-language, full multilingual, code, and long-document results differ enough to make per-domain comparison essential. |
| [Arctic Embed2.0 medium](https://huggingface.co/Snowflake/snowflake-arctic-embed-m-v2.0), [large](https://huggingface.co/Snowflake/snowflake-arctic-embed-l-v2.0) | 305M/568M; 768/1024 dimensions, reducible to 256; 8K | Apache-2.0 | Efficient multilingual alternatives with documented vector compression. The medium model's query prefix, pooling, truncation, and normalization must remain consistent. |
| [BGE-M3](https://huggingface.co/BAAI/bge-m3) | About 568M; 1024 dimensions; 8K | MIT | Useful established multilingual/hybrid control. Its dense, sparse, and multivector functions are distinct; an ordinary dense embedding endpoint does not provide all three. |

Two older Nomic options remain useful controls: [v1.5](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5)
is Apache-2.0, roughly 137M, 768 dimensions with reduction, and nominally 8K;
[v2-MoE](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe) is Apache-2.0,
475M total/305M active parameters, multilingual, and **512 tokens**. The latter
is not a long-context replacement for v1.5. Their task prefixes and normalization
procedures matter.

[Jina v5 small](https://huggingface.co/jinaai/jina-embeddings-v5-text-small)
and nano are current comparators, but their CC-BY-NC license requires a separate
commercial arrangement for commercial local use. Jina v2's Apache license does
not carry forward to v3/v5. NV-Embed-v2 is likewise CC-BY-NC. These are not freely
commercial local supplements merely because their weights are downloadable.

### What distinguishes the strongest embedding comparisons

Perplexity's [paper](https://arxiv.org/html/2602.11151v1#S3) reports multilingual
and code retrieval results close enough to make a Qwen0.6B/pplx0.6B comparison
more useful than declaring a winner. Its internal scale experiments include
millions of query or web-document candidates. Those use private
production-derived corpora and proxy relevance labels; they strengthen the case
for investigating scale, without qualifying broad personal or engineering memory.
Binary output also loses quality relative to its int8 results, so compression
is a tradeoff.

LightOn's [comparison](https://huggingface.co/lightonai/mDenseOn) gives different
relative results across BEIR, multilingual retrieval, long documents, and code.
Voyage-nano's code result is more competitive than its general BEIR result.
IBM's [Granite results](https://huggingface.co/ibm-granite/granite-embedding-311m-multilingual-r2)
similarly separate retrieval, code, long-input, and reasoning tasks. I would use
these slices to choose challengers; their different task sets do not form one
comparable leaderboard.

[RTEB](https://huggingface.co/blog/rteb) adds legal, healthcare, finance, and code
datasets, including private evaluation datasets intended to reduce training
contamination. Some constituent sets are still small or repurposed from QA.
Together with BRIGHT and code/multilingual retrieval suites, it is a better
source of challenge criteria than a general MTEB average. It still does not
represent the full proposed memory store.

Nemotron's [card](https://huggingface.co/nvidia/Nemotron-3-Embed-8B-BF16)
reports 78.46 nDCG@10 on 16 public RTEB tasks and 75.45 on MMTEB retrieval,
using a 4096-token evaluation limit. Harrier27B's multilingual aggregate is a
serious alternative, but its larger footprint and differing benchmark coverage
matter. Neither result demonstrates recall at 100K heterogeneous memories.
[Octen-Embedding-8B](https://huggingface.co/Octen/Octen-Embedding-8B) is another
Apache-2.0 challenger; its card's conflicting context limits and documented
prefix workaround need reconciliation before a fixture is frozen.

The private RTEB ranking also has a disclosed structural conflict: MTEB
maintainers [removed its private column](https://github.com/embeddings-benchmark/mteb/issues/3934)
because Voyage helped develop the benchmark and has direct access to private
data. They do not allege misuse. Results using evolved prompts or larger output
dimensions must also be distinguished from the default API configuration.

## Reranking candidates

| Candidate | Published scope and license | Why I would consider it; material tradeoff |
| --- | --- | --- |
| [Qwen3-Reranker-0.6B](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B) | 0.6B; 32K; 100+ languages; Apache-2.0 | Balanced multilingual/code candidate with task instructions and a yes/no scoring contract. That contract differs from zerank's selected-token scoring; reuse needs an explicit adapter contract. |
| [Ettin68M](https://huggingface.co/cross-encoder/ettin-reranker-68m-v1), [150M](https://huggingface.co/cross-encoder/ettin-reranker-150m-v1) | English; approximately 8K; Apache-2.0 | Strong compact challengers for fast English recall. The release evaluates full English retrieval tasks across six first-stage retrievers, plus separate NanoBEIR tests. Their English scope is a limitation for multilingual memories. |
| [Ettin17M/32M](https://huggingface.co/blog/ettin-reranker) | English; approximately 8K; Apache-2.0 | CPU-oriented speed controls. The publisher reports substantially better CPU throughput than larger models; exact host latency and long-tail quality remain unmeasured. |
| [Qwen3-Reranker-4B](https://huggingface.co/Qwen/Qwen3-Reranker-4B) | 4B; 32K; multilingual; Apache-2.0 | Larger difficult-query comparator. Published retrieval/code/instruction results support investigating it, but per-candidate compute makes it a poor automatic choice for every recall request. |
| [GTE ModernBERT reranker](https://huggingface.co/Alibaba-NLP/gte-reranker-modernbert-base) | About 149M; English; 8K; Apache-2.0 | Compact alternative with explicit code and long-context retrieval evidence. Useful alongside Ettin when those domains matter. |
| [BGE-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) | About 568M; multilingual; Apache-2.0 | Established multilingual control and the parent of the existing ordinary-rerank GGUF fixture. Compatibility of that retained fixture does not qualify every new conversion. |
| [mxbai-rerank-base-v2](https://huggingface.co/mixedbread-ai/mxbai-rerank-base-v2) | About 494M; 100+ languages; Apache-2.0 | Additional multilingual/code challenger. Published tables use different retrieval conditions from other publishers, so their headline scores are not directly interchangeable. |
| [Querit](https://huggingface.co/Querit/Querit), [Querit4B](https://huggingface.co/Querit/Querit-4B) | MoE 4.92B total/0.43B active or dense 4.02B; 128K; Apache-2.0 | Newer multilingual research comparators. Activated parameters are not resident weight size. The MoE's custom runtime and unusually small Hub safetensors metadata need closure investigation before treating it as a practical deployment candidate. |

[Jina-reranker-v3.5](https://huggingface.co/jinaai/jina-reranker-v3.5) is a current
0.6B listwise comparator with domain, multilingual, and structured-data results.
It is CC-BY-NC locally; commercial licensing or a service agreement is separate.
Its listwise interface scores a group jointly rather than independently scoring
each pair, so changing list size and ordering is part of later qualification.
The retained zerank-2 fixture remains the noncommercial comparator.

The [Ettin release](https://huggingface.co/blog/ettin-reranker) is unusually useful
speed evidence because it names hardware, token truncation, precision, attention,
and batch selection. Its 150M model reports 3237 pairs/s on H100 and 982 on RTX
3090; the benchmark truncates to 512 tokens and chooses the best batch through
an automatic sweep. These are throughput measurements, not single-query latency
or Strix Halo predictions. The CPU comparison uses an Intel i7-13700K and favors
17M/32M. The advertised approximately 8K encoder context also differs from the
released 150M config's 7999-position value; freeze the actual serving limit later.

Qwen's reranker [evaluation](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B#evaluation)
uses the top 100 candidates from Qwen3-Embedding-0.6B. Ettin's multi-retriever
comparison is broader on that axis, but English-only. Neither establishes the
best reranker for a multilingual, temporal, mixed-domain memory corpus.

### Hosted reranking frontier

[Voyage rerank-3 and rerank-3-lite](https://blog.voyageai.com/2026/09/30/rerank-3/)
launched on September 30. The publisher compares 95 datasets across nine domains,
including technical documentation, code, law, medicine, finance, multilingual
text, and conversations. It evaluates the top 100 candidates from four
first-stage retrievers and adds instruction-following tests. That breadth makes
full rerank-3 my current unrestricted-quality contender and lite my inexpensive
contender; these remain publisher evaluations without independent replication
or a large-memory test.

Both have 32K context. Current [pricing](https://docs.voyageai.com/docs/pricing)
is $0.05/M processed tokens for full and $0.02/M for lite. The
[billing rule](https://docs.voyageai.com/docs/reranker) counts query tokens once
per document plus document tokens. Reranking 100 documents with 500 combined
query/document tokens per pair therefore processes 50K tokens: $0.0025 full or
$0.001 lite. Repeated retrieval passes increase that cost.

[Cohere Rerank4](https://cohere.com/blog/rerank-4) provides a current enterprise,
multilingual, and structured-document comparison. Jina3.5's
[publisher evaluation](https://jina.ai/news/jina-reranker-v3-5-faster-listwise-reranking-hybrid-attention-self-distillation/)
also supplies useful domain slices. These comparisons do not all use the same
retriever, corpus, context, or metric. For local routine recall, I would compare
Qwen4B against the smaller Qwen0.6B and Ettin candidates before accepting its
per-candidate compute cost; a larger model's quality may not compensate for
slower recall under shared load.

## What Hindsight's rankings establish

The current [embedding](https://benchmarks.hindsight.vectorize.io/leaderboard/embeddings)
and [reranker](https://benchmarks.hindsight.vectorize.io/leaderboard/reranker)
boards use one LoCoMo conversation and roughly 165 scored questions. Their
composite scores weight MRR at 70%, speed at 15%, and cost at 15%. Local cost
receives a perfect score without hardware or operating costs. First overall is
therefore not necessarily first on retrieval quality.

The [published scoring source](https://github.com/vectorize-io/hindsight-benchmarks/blob/55c51f1d6e2477ee69c0a730a80b96a1596ff475/benchmark-runner/src/hindsight_benchmark/embeddings.py)
and [orchestration](https://github.com/vectorize-io/hindsight-benchmarks/blob/55c51f1d6e2477ee69c0a730a80b96a1596ff475/benchmark-runner/run_all_embeddings.py)
show additional limits: relevance labels depend on an initial retrieval pass;
questions with no annotated relevant facts are skipped; embedding models have
separate retained banks and labels; observations and causal extraction are
disabled; the runtime image uses a mutable tag. These factors weaken attribution
of small differences to the embedding model alone. The reranker page itself
cautions about lexical bias and generalization.

The 300-candidate setting is the **reranking shortlist**, not the bank size.
Returned context has a separate 8192-token cap. The board's R@K asks whether at
least one relevant fact was retrieved; it does not establish complete evidence
retrieval for multihop answers. Its measured recall time is end-to-end recall,
not isolated encoder latency.

Broader [Agent Memory Benchmark](https://agentmemorybenchmark.ai/) system tests
now cover long histories, including BEAM tiers up to 10 million tokens and
multiple memory abilities. Those are useful system evidence, but token counts
are not retained-memory counts, and these runs do not supply the missing
embedding/reranker head-to-head at 100K heterogeneous memories. The Hindsight
homepage and AMB overview also show different selected BEAM headline results;
bind any quoted result to its actual run rather than combining summaries.

## Retention models and latency

The current [retain board](https://benchmarks.hindsight.vectorize.io/leaderboard/retain)
uses four BEAM conversations and 80 questions, extracted facts only, and a fixed
answering/judging model. Its composite includes quality, stored-token efficiency,
speed, schema conformance, and cost. Local rows were measured on RTX PRO 6000,
not Strix Halo. This is useful evidence about structured extraction and reasoning
settings, not a general ranking for the requested domains.

The direct retain evidence supports comparing GPT-OSS-20B at low reasoning
effort and Qwen3.6-35B-A3B locally. Their reported facts-only QA results are
roughly 47.5% and 48.8%; the sample does not robustly distinguish that small gap.
More reasoning is not automatically better retention: GPT-OSS low and medium
produce different quality and latency on this board.

The [reflect board](https://benchmarks.hindsight.vectorize.io/leaderboard/reflect)
uses Hindsight v0.4.13, one LoCoMo conversation, 242 questions, fixed Gemini2.5
Flash retention, and Gemini2.5 Flash-Lite judging. GPT-OSS-20B/120B via Groq both
report 94.2% accuracy and mean full-reflect times of 2.8/2.2 seconds. These are
provider/system measurements involving potentially multiple calls, not local
decode latency. The board's listed prices are older than the current Groq pages.
No inspected benchmark separately establishes observation-consolidation quality.

### Local generative slate

[Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) and
[Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B) declare Apache-2.0,
thinking/non-thinking modes, tools, and MTP. Their cards include serving examples;
these do not establish the required local main/draft route or speedup. The 35B
MoE activates about 3B parameters per token; all weights still need residency.
[Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B) is dense and reports stronger
results on several general knowledge/reasoning measures. That is the basis for
my local consolidation/synthesis recommendation, not a memory-specific victory.
Their advertised native 262,144-token contexts do not establish practical local
context with shared memory, KV cache, concurrent services, and this backend.

[GPT-OSS-20B/120B](https://openai.com/index/introducing-gpt-oss/) are Apache-2.0
text-only MoE alternatives with configurable reasoning, tools, and structured
outputs. They require Harmony formatting. OpenAI's native MXFP4 memory estimates
are serving-configuration estimates, not guaranteed GGUF or Strix Halo fit.
The 120B model is a larger contender; its active parameter count is not resident
weight size. [Gemma4](https://huggingface.co/google/gemma-4-E2B-it) is another
Apache-2.0 family to compare. E2B's 2.3B effective count corresponds to 5.1B total
including embeddings; it must not be mistaken for a smaller resident 2B model
or a proved coherent replacement for the 4B fixture.

### Hosted generative slate

These are current standard text API prices in USD per million input/output
tokens, before cache, batch, tool, or service-tier effects. Large contexts can
change rates. A single memory operation may make several calls and pay for
reasoning output; headline token rates do not settle total cost or latency.

| Candidate | Input / output | Why it belongs in the comparison |
| --- | --- | --- |
| [GPT-OSS-20B / Groq](https://console.groq.com/docs/model/openai/gpt-oss-20b) | $0.075 / $0.30 | Cheapest primary generative contender in this slate, with direct older memory-task evidence; provider speed claims are not measured operation latency. |
| [GPT-OSS-120B / Groq](https://console.groq.com/docs/model/openai/gpt-oss-120b) | $0.15 / $0.60 | Larger low-cost comparison with direct reflect evidence. |
| [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) | $0.10 / $0.50 at ≤272K input; $0.20 / $0.75 above | Current low-cost proprietary alternative; no inspected memory-task comparison. |
| [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) | $2 / $10 at ≤272K; $4 / $15 above | Quality/value challenger between the inexpensive and ceiling candidates. |
| [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) | $10 / $50 at ≤272K; $20 / $75 above | Primary quality-ceiling contender from current general capability evidence. |
| [Claude Sonnet5.5 / Opus5.5 / Fable5.1](https://platform.claude.com/docs/en/models/overview) | $2/$10; $4/$20; $10/$50 respectively | Current Claude range; Fable is the primary ceiling comparison. Publisher model positioning is not memory-specific evidence. |
| [Gemini3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) | $0.75 / $3.75 through 2026-12-31; $1.50 / $7.50 from 2027-01-01 | Current stable Google contender with tools, structured outputs, and configurable thinking. |

Price sources: [Groq20B](https://console.groq.com/docs/model/openai/gpt-oss-20b),
[Groq120B](https://console.groq.com/docs/model/openai/gpt-oss-120b),
[OpenAI](https://developers.openai.com/api/docs/pricing),
[Claude](https://platform.claude.com/docs/en/models/overview), and
[Google](https://ai.google.dev/gemini-api/docs/pricing).
Google's newly announced [Gemini4 Argon](https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-4-argon/)
is a watchlist item: the announcement describes restricted Fairwind rollout,
with broader developer availability to follow.

Schema support, thinking settings, tool conventions, and the actual memory
adapter must align. For example, GPT-OSS requires Harmony; Claude Opus/Fable
restrictions on forced tool use can affect integrations that express extraction
schemas as tools. Valid JSON does not prove faithful fact extraction or conflict
handling. These are qualification criteria, not observed failures.
[Claude capabilities](https://platform.claude.com/docs/en/models/overview),
[structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).

[Performance documentation](https://hindsight.vectorize.io/developer/performance)
identifies extraction-model throughput and CPU reranking as major bottlenecks.
Its typical latency and large-bank claims omit enough hardware/workload details
that I would not use them as an operating budget. Useful retention comparisons
must distinguish queue acknowledgment, searchable facts, and completed
consolidation. Extraction, entity work, retries, embeddings, database writes,
and consolidation can each dominate; a fast encoder alone does not settle this.

## Capacity and serving implications

The table below is arithmetic, not a measured memory footprint. It assumes one
vector per memory and excludes text, metadata, graph/index overhead, temporary
buffers, model weights, and concurrent requests. MB means decimal megabytes.

| 100K vectors | float32 raw | int8 raw |
| --- | ---: | ---: |
| 384 dimensions | 153.6 MB | 38.4 MB |
| 768 dimensions | 307.2 MB | 76.8 MB |
| 1024 dimensions | 409.6 MB | 102.4 MB |
| 2048 dimensions | 819.2 MB | 204.8 MB |
| 4096 dimensions | 1638.4 MB | 409.6 MB |

Multiply by three for 300K vectors. Multiple chunks, extracted facts, and
observations per input multiply both storage and indexing work. Matryoshka
dimension reduction lowers vector storage and search arithmetic; it generally
does not lower the encoder's transformer work. Vector precision and weight
quantization are different choices.

Hindsight's current [model documentation](https://hindsight.vectorize.io/developer/models)
and embedding benchmark apply a 2000-dimension vector-HNSW constraint. Qwen4B,
pplx4B, Voyage-nano's full output, and other larger outputs therefore need a
supported reduced-dimension route or another qualified index representation.
Changing model space requires re-embedding and migration even when dimensions
match; existing vectors from different models must not be silently mixed.

Publisher integration examples provide leads, not local qualification. Qwen
publishes embedding GGUFs. Granite supplies conversion and ONNX/OpenVINO routes.
Voyage and Perplexity require their bidirectional/pooling contracts, and Gemma
requires projection layers. A generic causal, last-token Qwen loader is not an
adequate substitute. The retained zembed role's last-token invariant also does
not apply automatically to these supplemental memory-design candidates.

## Hosted embedding frontier

[Voyage4](https://docs.voyageai.com/docs/embeddings) supports a publisher-declared
shared space with local nano. An asymmetric document/query setup is worth
investigating, but local parity is unproven. Current
[prices](https://docs.voyageai.com/docs/pricing) are $0.12/M tokens for large,
$0.06/M for standard, and $0.02/M for lite.
[Perplexity](https://docs.perplexity.ai/docs/embeddings/standard-embeddings)
prices 0.6B at $0.004/M and 4B at $0.03/M; 50M input tokens would cost $0.20
for 0.6B encoding alone, excluding extraction, reranking, storage, and operation.

[Cohere Embed5](https://cohere.com/blog/embed-5), launched September 30, supports
128K context and outputs from 256 to 2048 dimensions. Pro/Fast share a space and
cost $0.12/$0.08 per million text tokens. Its parsed-text ViDoRe3 results report
85.8 for Pro versus 83.7 for Voyage4-large, using a new **RCP-nDCG@10** method.
That cannot be pooled with conventional fixed-label nDCG scores. Parser effects,
undisclosed additional datasets, and the lack of independent replication make
this a provisional ceiling choice. Voyage remains the essential text-retrieval
comparison. [OpenAI embedding3](https://developers.openai.com/api/docs/guides/embeddings)
small/large provide additional hosted controls.

Commercial provider terms, retention policies, residency, request latency, and
full operating costs need separate qualification. No private memory content
was sent to a provider, and no paid trial was performed.

## The evidence still needed

No inspected public comparison establishes a universal best model for this
large, varied memory store. My shortlist separates balanced, fast, and difficult
query candidates so a later comparison can resolve the practical tradeoff.
It does not make every candidate an implementation or package lane.

When custom evaluation is taken up, the useful measures are candidate recall,
final ranking and multihop evidence completeness, per-domain failures,
single-query latency under shared load, indexing throughput, and time to
searchable/consolidated memory. Corpus size should count memories, facts,
chunks, and vectors separately. Rare identifiers, similar entities, legal and
scientific qualifiers, changed decisions, contradictions, negation, dates,
multilingual queries, and source-quote recovery deserve coverage. Compression,
query formatting, extraction settings, and ANN approximation should be varied
separately rather than credited to one model score. None of those evaluations
were run in this survey.
