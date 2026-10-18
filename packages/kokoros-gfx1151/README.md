# kokoros-gfx1151

## Maintenance Snapshot

- Role: `tts-runtime`
- Recipe package key: `lemonade`
- Scaffold template: `kokoros`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/lemonade-sdk/Kokoros.git`
- Package version: `b17`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `34, 35, 36`
- Recipe dependencies: `therock, llamacpp`
- Recorded reference packages: `none`
- Authoritative reference package: `none`
- Advisory reference packages: `none`
- Applied source patch files/actions: `1`

## Recipe notes

Kokoros is the Rust Kokoro text-to-speech server that Lemonade runs for its
kokoro recipe. The ai-notes recipe has no Kokoros entry; this package is
repo-local and belongs to the Lemonade family.


## Scaffold notes

- Pinned to the GitHub archive of lemonade-sdk/Kokoros commit d122b52e0ee0a90df26fd041620af36f99e2248a (tag b17) with its sha256; prepare() applies the source patches, then checks Cargo.lock against cargo_lock_sha256 before cargo fetch --locked, following Arch's Rust packaging guidelines, and build() runs cargo build --frozen --offline. The patches do not touch Cargo.toml or Cargo.lock, so --locked and --frozen still hold.
- The build must not reach the network beyond the locked crates. ort-sys would otherwise download a prebuilt ONNX Runtime: build() sets ORT_LIB_LOCATION=/usr/lib, ORT_PREFER_DYNAMIC_LINK=1, ORT_SKIP_DOWNLOAD=1, and CARGO_NET_OFFLINE=true, and points XDG_CACHE_HOME into $srcdir. The bundled espeak-ng would otherwise clone sonic with CMake FetchContent; libsonic in makedepends lets its find_library succeed. Disabling ort's default features would change Cargo.lock, which --locked and --frozen forbid, so the environment carries the guarantee.
- check() fails the build if ort-sys left a dfbin download directory anywhere under $srcdir, if a _deps/sonic-git* directory appears under the build tree, or if koko's ELF NEEDED entries lack libonnxruntime.so, libopus.so, or libsonic.so.
- Installs /opt/kokoros-gfx1151/koko and /opt/kokoros-gfx1151/espeak-ng-data. lemonade-server's package env file sets LEMONADE_KOKORO_CPU_BIN=/opt/kokoros-gfx1151/koko, so lemond uses this binary instead of downloading a Kokoros release; with offline and no_fetch_executables set, its install step uses the configured binary.
- Installs Kokoros' README (its only licence statement at this commit), the licence files of every crate linked into koko from the fetched crate sources, and LAME's COPYING. package() fails if cargo tree fails or lists no crates, or if it lists a crate other than Kokoros' own path crates that has no fetched registry source (a git-sourced crate, for example), so no crate is skipped silently. Arch's common licences cover the GPL-3.0, LGPL, and Apache-2.0 texts.
- Keeps model and voice files out: they are #107's model contract (see the update notes). The renderer refuses to render this package without 0001-koko-fail-closed-on-missing-model-files.patch, which turns koko's download of a missing kokoro-v1.0.onnx or voices-v1.0.bin into an error, and prepare() fails if the download call survives patching.

## Intentional Divergences

- No Arch, CachyOS, or AUR package builds Kokoros; AUR python-kokoro is the unrelated Python implementation, so this package has no reference baseline.
- Builds the lemonade-sdk/Kokoros b17 commit that Lemonade's backend_versions.json pins, from source, instead of installing upstream's kokoros-linux-x86_64.tar.gz release binary.
- Links the system onnxruntime-cpu library dynamically, where upstream's release binary statically links the prebuilt ONNX Runtime 1.23.2 that ort-sys downloads at build time.
- Links the system opus and libsonic, where upstream's build compiles audiopus_sys's bundled opus and clones sonic into espeak-ng's build; espeak-ng and LAME stay bundled because their crates offer no system-library option.
- Installs koko and espeak-ng-data together under /opt/kokoros-gfx1151, the layout lemond expects: it derives ESPEAK_DATA_PATH and LD_LIBRARY_PATH from the binary's directory.
- Removes koko's built-in model and voice download: upstream fetches a missing kokoro-v1.0.onnx or voices-v1.0.bin from GitHub, and this package's patch makes a missing file an error.

## Update Notes

- Track the Kokoros release that Lemonade's src/cpp/resources/backend_versions.json pins for kokoro.cpu at the packaged Lemonade commit; repin this package together with that Lemonade pin.
- Generation C W2B (#113): adopted lemonade-sdk/Kokoros b17 at d122b52e0ee0a90df26fd041620af36f99e2248a, which Lemonade b6616eb3 pins. Recorded the commit archive sha256 and the Cargo.lock sha256; prepare() runs cargo fetch --locked and build() runs cargo build --frozen --offline. Open gates: not yet built. The ort 2.0.0-rc.11 crate uses ONNX Runtime C API version 23 and links the onnxruntime-cpu 1.29 shared library; that pairing is untested, and the installed smoke test must prove that koko loads a model and synthesizes speech. -C link-arg=-lsonic is in RUSTFLAGS because espeak-rs-sys names only speechPlayer, espeak-ng, and ucd to the linker; whether the link needs it is confirmed only at build time, and if the build proves it unnecessary, remove it then.
- Model and voice files are not part of this package; they belong to #107's model contract. Upstream koko downloads kokoro-v1.0.onnx and voices-v1.0.bin from the thewh1teagle/kokoro-onnx model-files-v1.0 release when the paths lemond passes with -m and -d do not exist. By owner decision on 2026-10-18, 0001-koko-fail-closed-on-missing-model-files.patch removes that fallback: a missing file stops koko with an error naming the file and never starts a download, and prepare() fails if koko.rs still calls download_file_from_url after patching. #107 must still prove on the installed stack that absent files fail without egress, and its contract must keep both files present. Lemonade's kokoro-v1 catalog entry names Hugging Face mikkoph/kokoro-onnx, whose index.json lists exactly those two files. On every repin, rebase the patch and check the new source for any other download path (download_file_from_url, reqwest).

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
