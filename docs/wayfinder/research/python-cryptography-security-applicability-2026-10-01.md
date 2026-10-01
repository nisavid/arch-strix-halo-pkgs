# CPython and cryptography security applicability

This report gives the foundation and drift owners evidence for a security
exception to the September 22 generation C freeze. I recommend admitting a
CPython security update to the foundation review and making an explicit
early-maintenance decision for cryptography's X.509 fixes. Neither recommendation
selects a source, changes C, or authorizes a host operation.

The investigation belongs to [Assess CPython and cryptography security
applicability before generation C](https://github.com/nisavid/arch-strix-halo-pkgs/issues/170).
Primary sources and local static evidence were collected on 2026-10-01.
No exploit test, package build, import smoke, inference, service operation,
installation, or snapshot was run. The findings concern affected versions and
conditional exposure; no local exploitability claim is confirmed.

## Subjects and evidence boundary

| Subject | Reviewed identity | What the evidence establishes |
| --- | --- | --- |
| Research branch base | `9c2a53c911bee6cc70a44bc6e8edfde86a12b84a` | Package metadata and the frozen selection on the published default branch |
| Foundation F, PR 149 | `b8ee7d6d2576683ee142fb39cc36eeb2709bb175` | CPython 3.14.7-1 recipe, source patch, configuration, and reported staged validation |
| W2A closure | `df6c8f16713d882899559400fe4d39714a26c999` | Latest reviewed freshness narrative, candidate disposition, and build-root tools |
| Completed sweep | `d1935e4c1488367ba2cd8a41597247a5d8548a89`, completed `2026-10-01T01:16:27Z` | Discovery and matched ledger disposition; no CPython 3.14.8 security adjudication |
| Host package inventory | Read-only `pacman -Q` during this investigation | `python-gfx1151` 3.14.6-1; `python-cryptography-gfx1151` 48.0.0-1; Expat 2.8.3-1.1; OpenSSL 3.6.3-1.1 |
| Installed caller samples | pip 26.2.1-1, AnyIO 4.14.2-1, urllib3 2.7.0-1, Samba 2:4.24.6-1.1 | Static extraction, TLS, and certificate-loading callers described below |

The foundation recipe's
[`packages/python-gfx1151/PKGBUILD`](https://github.com/nisavid/arch-strix-halo-pkgs/blob/b8ee7d6d2576683ee142fb39cc36eeb2709bb175/packages/python-gfx1151/PKGBUILD#L24)
removes bundled Expat and configures `--with-system-expat`. It depends on
system OpenSSL, bzip2, zstd, and the other normal interpreter libraries;
LZMA is an optional `xz` integration. It enables shared libraries, PGO, and
LTO, with no `--disable-gil` option. None of the supplied core advisories is
limited to free-threaded Python or defeated by these optimization flags.
Its only source patch is the POSIX-2024 build backport, not a security fix.

The cryptography
[`PKGBUILD`](https://github.com/nisavid/arch-strix-halo-pkgs/blob/9c2a53c911bee6cc70a44bc6e8edfde86a12b84a/packages/python-cryptography-gfx1151/PKGBUILD#L14)
builds the 48.0.0 source distribution with Rust and setuptools-rust and declares
system OpenSSL. Installed ELF metadata shows `_ssl` and cryptography's Rust
extension needing `libssl.so.3` and `libcrypto.so.3`; `pyexpat` needs
`libexpat.so.1`. This is dependency evidence, not observation of a running
process's loaded libraries or OpenSSL providers.

`codex-security:triage-finding`'s security-policy resolver returned no applicable
`SECURITY.md` for either package directory. Package metadata establishes shipped
system interpreter and library APIs. It does not establish every consumer's
trust model, supported configuration, or input provenance. Those gaps prevent
an affected-version match from becoming a confirmed boundary-crossing finding.

## CPython 3.14.8 over foundation 3.14.7

[Python's release page](https://www.python.org/downloads/release/python-3148/)
identifies 3.14.8, released September 30, as an expedited security release.
The [release changelog](https://docs.python.org/release/3.14.8/whatsnew/changelog.html#python-3-14-8-final)
also contains ordinary fixes. Admission would require reviewing the whole
selected source delta, not assuming this is a security-only patch set.

The five rows below marked **stable 3.14 range** have PSF CNA affected versions
`3.14.0 <= version < 3.14.8`; both 3.14.6 and 3.14.7 match. The other series'
bounds are in each linked CNA record. The two exceptional ranges are preserved
explicitly. Verdicts apply to the local claim, not to whether upstream fixed a bug.

| Imported finding | Version evidence and trigger | Local evidence, counterevidence, and proof gap | Static verdict / confidence / review rank |
| --- | --- | --- | --- |
| [CVE-2026-19445](https://cveawg.mitre.org/api/cve/CVE-2026-19445), [gh-156293](https://github.com/python/cpython/issues/156293) | **Stable 3.14 range.** Server SNI callback switches `SSLSocket.context` without retaining the original context, allowing use after free. | `_ssl` ships. A malicious handshake matters only on a server with the stated callback/lifetime pattern. Clients and servers retaining the context are counterexamples. No supported local server with that pattern was established. | `needs_review`, low, 3 |
| [CVE-2026-19553](https://cveawg.mitre.org/api/cve/CVE-2026-19553), [gh-156793](https://github.com/python/cpython/issues/156793) | **Stable 3.14 range.** `wrap_bio()` can skip hostname verification with `check_hostname=True` when the hostname is absent. CNA also names asyncio TLS APIs. | Installed AnyIO and urllib3 reach `wrap_bio()`. Both pass a hostname argument; AnyIO uses IDNA 2008 for supplied names. A valid nonempty hostname defeats this claim. No client configuration with checking enabled and an absent hostname was established. The fix makes that configuration raise `ValueError`. | `needs_review`, medium, 2 |
| [CVE-2026-82049](https://cveawg.mitre.org/api/cve/CVE-2026-82049), [gh-157190](https://github.com/python/cpython/issues/157190) | CNA's 3.14 interval is **3.14.0a1 to before 3.14.0b1**, excluding both stable subjects. Crafted hard-link-to-symlink archives can affect outside-file metadata or disclose contents in older branches. | The release page lists the CVE, but the CNA and upstream issue explain the incidental 3.14 fix. This is positive version counterevidence, not absence of an extraction caller. It does not defeat either other tarfile advisory. | `not_actionable`, high, unranked, for these two stable CPython subjects |
| [CVE-2026-15310](https://cveawg.mitre.org/api/cve/CVE-2026-15310), [gh-156002](https://github.com/python/cpython/issues/156002) | **Stable 3.14 range.** bzip2, LZMA, and Zstandard ZIP members can exhaust memory through unbounded decompressor output despite small reads. | pip uses `ZipFile`; the recipe enables relevant library integrations. DEFLATE is upstream counterevidence for ordinary wheels. No supported attacker-controlled ZIP path using an affected codec was established, and LZMA availability in F was not independently inventoried. | `needs_review`, medium, 6 |
| [CVE-2026-19672](https://cveawg.mitre.org/api/cve/CVE-2026-19672), [gh-155999](https://github.com/python/cpython/issues/155999) | POSIX `tar`/`data` filters can create **empty directories** outside the destination through exit-and-reentry paths. CNA still says `0 <= version < 3.16.0`; 3.14.8's changelog says the fix is included. | Installed pip calls `tar.extractall(..., filter=pip_filter)` and delegates to `data_filter`. Contents remain contained per CNA. A secure randomized destination defeats the precondition; destination predictability for supported uses was not established. The source/changelog versus CNA fixed-range disagreement needs reconciliation before declaring a selected replacement unaffected. | `needs_review`, medium, 1 |
| [CVE-2026-15806](https://cveawg.mitre.org/api/cve/CVE-2026-15806), [gh-155694](https://github.com/python/cpython/issues/155694) | **Stable 3.14 range.** `HTTPPasswordMgr` and subclasses match credentials across URL schemes; a downgrade can disclose credentials. | Installed `reduce_uri()` returns authority and path without scheme. Repo tools use `urlopen`, but no configured password manager was found in that scoped code. An ordinary request is insufficient proof. Need a credential-registering consumer and scheme transition. The fix still permits bare-authority credentials to match any scheme. | `needs_review`, medium, 7 |
| [CVE-2026-17084](https://cveawg.mitre.org/api/cve/CVE-2026-17084), [gh-155292](https://github.com/python/cpython/issues/155292) | **Stable 3.14 range.** RFC 3454 B.2/B.3 StringPrep processing uses attributes newer than Unicode 3.2.0. Applies to particular IDNA 2003 character inputs. | `stringprep` ships; its Unicode-3.2 import alone is insufficient to defeat the mapping issue. AnyIO explicitly uses IDNA 2008 for supplied hostnames. Need a supported IDNA 2003 consumer and externally influenced affected name; no specific authentication or disclosure consequence was established locally. | `needs_review`, low, 8 |
| [gh-158446](https://github.com/python/cpython/issues/158446) | Extreme float/complex format precision near `INT_MAX` can crash or produce incorrect output; release lists its correction. No CVE or affected-version interval was supplied. | Interpreter formatting ships. No externally influenced precision parameter reaching the affected operation was established. Treat as release security content with a caller gap, not an invented CVE or remote-code-execution claim. | `needs_review`, low, 9 |
| [gh-157953](https://github.com/python/cpython/issues/157953), bundled Expat 2.8.5 | CPython updates its bundled copy. | F deletes that copy and uses system Expat; installed ELF metadata confirms the separate system dependency. This source bump cannot update host Expat 2.8.3. Independent Expat advisory triage is outside this ticket. | `not_actionable`, high, unranked, for the bundled-copy claim |
| [gh-158010](https://github.com/python/cpython/issues/158010), bundled OpenSSL 3.5.9 | Bundled update for Windows, macOS, Android, and iOS. | F is a Linux source build against system OpenSSL. A CPython bump cannot update host OpenSSL 3.6.3. Independent OpenSSL advisory triage is outside this ticket. | `not_actionable`, high, unranked, for the bundled-copy claim |

Ranks order the ten unresolved findings in this report by concrete caller evidence
and remaining preconditions, not by upstream severity. Rank 1 does not mean a
local exploit was demonstrated. No confirmed queue exists.

Two packaging paths provide narrower counterevidence. At the reviewed foundation
revision, `tools/stage_therock_payload.py:66` verifies the pinned payload's size
and SHA-256, and `:107` invokes system `tar`, not Python extraction. At the W2A
revision, `tools/c_buildroot.py:174` reads repository descriptions with
`extractfile()` without filesystem extraction. Neither settles arbitrary pip,
build-tool, model-library, or other host consumers.

## Additional host gap: 3.14.7 over 3.14.6

The host lacks the predecessor release too. Its
[security changelog](https://docs.python.org/release/3.14.8/whatsnew/changelog.html#id2)
lists HTML parser and ElementTree quadratic behavior (`gh-153030`, `gh-152674`),
tarfile link filtering, stream EOF, and symlink-filter corrections (`gh-151987`,
`gh-151981`, `gh-151558`), HTTP trailer/interim-response limits
(`gh-150743`, GHSA-w4q2-g22w-6fr4), configparser line-ending normalization
(`gh-143927`), IMAP command-character rejection (`gh-143921`), source-tree
detection (`gh-151544`), and a bundled Expat update (`gh-152216`). These are
predecessor release observations, not newly triaged findings or 3.14.8 changes.

F's 3.14.7 source already includes that predecessor set. The host's 3.14.6 does
not gain it from F being staged. Earlier host maintenance is therefore a separate
owner decision, requiring its own prepared build, validation, rollback, and
owner-run install. This report supplies no install command because no replacement
package was selected or built in this lane.

## cryptography 48.0.0

All three supplied advisory ranges include the installed 48.0.0. The first-party
pyca advisories give the X.509 fixed floor as 49.0.0 and the PKCS#7 floor as
50.0.0. The GitHub reviewed database gives more precise introduction bounds;
those bounds and pyca's broader X.509 `<=48.0.0` metadata agree for this subject.
Severity labels differ between pyca and the database, so severity alone does not
choose admission.

| Imported finding | Range, source/control/sink, and intended boundary | Evidence, counterevidence, and minimal proof gap | Static verdict / confidence / review rank |
| --- | --- | --- | --- |
| [CVE-2026-69249 / GHSA-jwv3-5hgf-82ww](https://github.com/pyca/cryptography/security/advisories/GHSA-jwv3-5hgf-82ww) | [Database](https://github.com/advisories/GHSA-jwv3-5hgf-82ww): `>=42.0.0,<49.0.0`. Duplicate self-signed intermediate certificates feed recursive `build_chain_inner` without valid-issuer deduplication; chain-depth termination does not prevent amplification. Intended property is verifier availability under untrusted chains. | Installed `cryptography/x509/verification.py` exports Rust `PolicyBuilder`, `Store`, and verifiers. No direct consumer appeared in the bounded Python-source search. Generic X.509 parsing, certificate generation, and stdlib/OpenSSL TLS do not establish use of this verifier. Need the actual verifier caller, intermediate source, depth policy, and workload bound. | `needs_review`, medium, 4 |
| [CVE-2026-69248 / GHSA-m2h6-j472-rp4c](https://github.com/pyca/cryptography/security/advisories/GHSA-m2h6-j472-rp4c) | [Database](https://github.com/advisories/GHSA-m2h6-j472-rp4c): `>=45.0.0,<49.0.0`. Wildcard SAN checking can exceed a constrained intermediate's permitted DNS subtree; a broad wildcard can authorize an outside name. Intended property is certificate authority scope containment. | The verifier API ships, but no direct installed caller was found. Need its trust roots, constraint-bearing intermediate, extension policies, accepted SANs, requested name, and attacker influence. Authentication reachability cannot be inferred from cryptography being a TLS-related dependency. | `needs_review`, medium, 5 |
| [CVE-2026-69247 / GHSA-g6cj-pr64-35w5](https://github.com/pyca/cryptography/security/advisories/GHSA-g6cj-pr64-35w5) | [Database](https://github.com/advisories/GHSA-g6cj-pr64-35w5): `>=44.0.0,<50.0.0`. Untrusted EnvelopedData reaches RSA key unwrapping, AES initialization, and distinguishable errors/timing. Repeated adaptive decryption responses can expose a content-encryption-key oracle. | Installed public functions alias Rust decrypt bindings. The bounded search found definitions, not direct consumers. Samba loads certificate bundles and does not invoke these decrypt functions. pyca distinguishes OpenSSL 3.2+ implicit rejection from older backends; the package inventory is 3.6.3 and ELF linkage is system OpenSSL, but provider behavior was not probed. Need a decrypting service, input provenance, reflected outcome, backend, and query opportunity before confirmation. | `needs_review`, medium, 10 |

For PKCS#7, the September 22 no-consumer record remains useful historical
counterevidence for its reviewed scope. It neither proves current exhaustive
absence nor answers the two X.509 claims. pyca also says unauthenticated
EnvelopedData's CBC padding-oracle property remains after the unwrap fix;
upgrading is not a general safe-decryption guarantee.

The [cryptography changelog](https://cryptography.io/en/latest/changelog/)
identifies the PKCS#7 fix in 50.0.0. Its 50.0.1 and 50.0.2 entries update upstream
wheels to OpenSSL 4.0.2 and 4.0.3, respectively; 50.0.2 also updates PyO3 and
free-threaded wheel support. Those entries do not establish that 48.0.0 is safe,
or that a source-built distribution package adopts the wheels' OpenSSL. The
49.0.0 changelog does not enumerate these two X.509 CVEs; the advisory fixed
version is the relevant evidence. A 49.x selection would leave the supplied
PKCS#7 finding unresolved; a validated 50.x selection covers all three reported
fix floors. Selection and compatibility review remain with the drift owner.

## Recommendations and next gates

For [Build and validate the W1 foundation
generation](https://github.com/nisavid/arch-strix-halo-pkgs/issues/108), I recommend
considering 3.14.8 under the existing security exception before accepting F.
Six CVE version conditions match F's interpreter, and archive/TLS consumers
exist on the host even though the full vulnerable configurations remain unproven.
The foundation owner should record admission or a bounded deferral with caller
evidence, review the full source delta and patch carry, and reconcile the
CVE-2026-19672 fixed-range disagreement. This recommendation does not amend the
[September 22 selection](c-line-selection-2026-09-22.md).

For [Absorb upstream drift deferred by the generation C version
freeze](https://github.com/nisavid/arch-strix-halo-pkgs/issues/147), I recommend an
explicit decision on earlier cryptography maintenance. The bounded search
supports conditional deferral, not a whole-host non-exposure finding. If the
owner defers, record the consumer scope and trigger for reopening: a verifier
processing untrusted chains or a decrypting consumer. If the owner admits it,
prepare and validate a source-built package before handing off host installation.
Being outside C's selected PyTorch/vLLM closure does not remove a system-wide
library's security obligations or automatically force it into C.

The W2A `current-state.md` narrative says the cryptography increment adds no
security fix and carries forward the PKCS#7 decision. Its ledger's salient
changes and the drift owner's later comment correctly name the X.509 advisories.
The disposition reason and next-gate label still describe post-closeout
maintenance. They should explicitly retain the unresolved security decision;
the newer changelog's small delta must not erase fixes between installed 48.0.0
and the proposed replacement.

The freshness checker can match CPython's newer result to an existing covered
check. A zero exit and a matched record are discovery/disposition mechanics,
not proof that 3.14.8 was security-reviewed. The completed sweep predates the
subsequent ledger change, which invalidates its cache digest. I did not rerun
broad discovery or alter the checker. The maintenance owner should record a
version-specific CPython security disposition, correct cryptography's decision
text, and run explicit tracker validation after any routing change. Keep active
gates on open issues; do not mark a candidate adopted before derived gates pass.

## Evidence invalidated by a selected source change

The [validation derivation workflow](../../maintainers/update-workflows.md#validation-gate-derivation)
requires changed artifacts and their consumers to be reassessed. These are
conditional obligations for the owners, not checks executed by this research.

| Selected change | Stale evidence and required replacement |
| --- | --- |
| CPython 3.14.7 to a new source | Old source digest, rendered metadata, patch applicability, PGO/LTO build, package archive identity, and interpreter/import smokes do not qualify the replacement. Re-render and build it; check the POSIX-2024 patch against the chosen source rather than applying it blindly. |
| Foundation containing a new interpreter archive | Replace F's archive/manifest identities and C root locks. Re-populate and verify the root's file ownership, dependency closure, ELF checks, and stale allowlist entries. Old F/MIGraphX and Python probes remain records of the old subject; repeat applicable probes against the replacement. |
| Python consumers and native extensions | Derive the graph with `tools/repo_package_graph.py` on the chosen final revision. Evaluate ABI/API, embedded/generated values, and build imports before deciding which consumers must rebuild. A patch release does not by itself prove either universal rebuild necessity or universal reuse safety. |
| Python runtime closure | Repeat affected in-root imports and documented torch, TorchVision, vLLM, Triton/AITER, Torch-MIGraphX, and model/runtime smokes or scenarios against the final interpreter and package lock. Retain an unchanged result only with explicit unchanged-dependency evidence. The existing W2A results cannot be relabeled as results for a changed interpreter. |
| C acceptance and activation | Repeat affected W4 prevalidation and later owner-run W5 install/W6 installed-smoke and live gates for the selected coherent transaction. Keep B0 restoration and the operation envelope with their owners. Security research cannot clear these gates. |
| cryptography 48.0.0 to a new source | Replace recipe/source checksum, backend/PyO3 compatibility evidence, build/archive identity, dependency and ELF linkage checks, and installed API/consumer smokes. Review 49.x/50.x API changes for actual consumers, including signing/certificate tooling such as Samba and systemd-ukify. Upstream wheel results do not qualify this source-built package. |
| Separate early host maintenance | New package transaction, rollback preparation, host interpreter/library inventory, installed smokes, and affected services/scenarios require owner-run execution. Reconcile the changed host baseline with B0 and later C preparation; do not reuse the old inventory as current evidence. |

Purely native TheRock binaries with proven unchanged inputs need not be rebuilt
solely because this report recommends an interpreter update. Their Python
bindings, launchers, probes, and the combined foundation acceptance still need
the affected-evidence analysis. Unrelated vLLM or stable-diffusion advisories
were not included in this lane.

## Reusing the procedure and reproducing the observations

Consumers should load `maintaining-arch-strix-halo-packages` from its maintained
repo skill and `codex-security:triage-finding` (reviewed plugin version 0.1.31)
before dependent work. The procedure is unchanged: normalize each supplied
advisory, resolve security policy, distinguish affected versions from supported
source/control/sink reachability, preserve counterevidence and proof gaps, then
derive affected validation gates. `capturing-agent-procedures` adds no new
global rule here. This dated report is the consumer input; source revision,
installed inventory, or advisory changes require a fresh applicability pass.

I searched repo `tools` and package source for the named API families and
searched installed Python 3.14 `site-packages` plus systemd-ukify for direct
X.509 verifier builders and PKCS#7 decrypt names/bindings. The result contained
cryptography's API definitions and related types, without direct consumer hits.
This search covers readable `.py` files in those locations. It excludes native
callers, aliases or dynamic dispatch that avoid those names, other environments,
user scripts, and the full transitive dependency source universe. It is not a
repository vulnerability scan or exhaustive host audit.

Installed file hashes bind the principal caller observations:

| Module | SHA-256 |
| --- | --- |
| `cryptography/x509/verification.py` | `811d82d9cf97650b5b959853e53e6f8d228eb426fbe1e7f66a53d59847301653` |
| `cryptography/hazmat/primitives/serialization/pkcs7.py` | `98533b385b99f1c0b1506528a380a87fa06708773f21bc750108e37f19cf971a` |
| `samba/gp/gp_cert_auto_enroll_ext.py` | `b56823666586b6608e6303302b95902629108faeef38f0a82ee301fb4b233d94` |
| `pip/_internal/utils/unpacking.py` | `e62f529fffd2344961a025e72edd92bd0690f929d3cdc51a0c7d7f248d531d4c` |
| `anyio/streams/tls.py` | `1afb3ef983a81717329fe85a9173a23ccf07f9a129f27b14ea4f6b4eb2aa240e` |
| `urllib3/util/ssltransport.py` | `133e0ef2947fbd3f1d6a7fc5bea0584ba7600df05710c7d57ebcdc754a167e2e` |

The background research helper collected primary release/CNA facts; advisory
triage was performed inline. Three CNA records with material distinctions
(CVE-2026-82049, CVE-2026-19672, and CVE-2026-19553) were independently reread
through the CVE Program API. Some announcement pages were unavailable; their
successfully retrieved PSF CNA records remain the version/condition sources.
The complete 3.14.8 and 3.14.7 security sections were retrieved through a bounded
HTTP range of the large changelog. No source archive was downloaded.

Research changed documentation only. Package source updated: no; package built:
no; deployed/installed: no; installed-smoked: no; live-scenario validated: no.
Foundation acceptance, owner security decisions, and normal publication/review
remain separate gates.
