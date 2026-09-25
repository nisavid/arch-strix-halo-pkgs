# Generation-C Build Root

Generation C (W2A, #98) builds the PyTorch and vLLM chain against the new
foundation F: TheRock 7.14.1, MIGraphX 2.16.1 and CPython 3.14.7. The host
still runs the previous generation (ROCm 7.13 under `/opt/rocm`, CPython
3.14.6, and a torch linked against 7.13). F must not be installed on the host
before W5, so W2A packages are built in a rootless bubblewrap root that holds F
at the paths the host will have after W5.

`tools/c_buildroot.py` owns this flow. Its data lives in `tools/buildroot/`:

| File | Purpose |
| --- | --- |
| `makepkg.conf` | The one makepkg.conf for root builds. `enter` binds it read-only at `/etc/makepkg.conf`. |
| `torch-chain.targets` | Targets for the torch-chain root (base-devel, build tools, F, the torch makedepends and the protobuf and Abseil floors that MIGraphX needs). |
| `py-closure.targets` | Extra build tools for the #110 model/runtime Python closure: meson-python, Cython, maturin, the Rust toolchain and `llvm`. Resolve it together with `torch-chain.targets` to build the closure. |
| `model-closure.targets` | The #110 closure packages as built into `ashp-w2a`. Resolve it together with `torch-chain.targets` to get a root that can import them. |
| `vllm-build.targets` | Build tools for the vLLM 0.30.0 package (#111): setuptools-rust, semantic-version, the Arch Rust toolchain, poetry-core and the build tools of the small closure packages that the vLLM lease job builds first. It also lists the Arch runtime closure for the in-root vLLM import and server smoke, and `procps-ng` for the scenario runner's `ps`. Resolve it together with `torch-chain.targets` and `model-closure.targets`. |
| `probe/` | The no-leak probe: a hipcc program, a CMake HIP library and a makepkg package. |

Nothing in this flow needs root, sudo or `pacman -S/-U/-Sy`, and nothing
writes to the host's pacman state. The tool reads the sync databases, the
package cache and `pacman -Q`, and it writes only under the paths you pass it.

## Why the root cannot leak 7.13

Every file in the root comes from a package file that the lock names, and the
root never sees the host's `/usr`, `/opt` or site-packages. Four layers keep
it that way:

1. **Resolution.** `resolve` reads sync databases in the order you give. The
   foundation repos (`--foundation-repo`, for example `ashp-w1-staging` and
   then `ashp-w2a`) always win over userland repos. That is how
   `rocm-core-gfx1151` 7.14.1 beats any same-named or same-provides package.
   The previous generation's repo is never passed as a `--db`; the tool
   refuses it if it is. It is passed only as `--forbid-db`, and every package
   name in that repo is barred from the host cache. That stops a cached 7.13
   `-gfx1151` file from entering under a matching name and version.
2. **Files.** Foundation packages come from their repo pools. All other
   userland comes at its sync DB version. The host's package cache is only a
   download cache: `resolve` uses a file there only when it is the file the
   sync DB names and its sha256 matches the DB entry. `fetch` downloads every
   other file from the host's configured mirrors and accepts it only when its
   sha256 matches the sync DB. The lock records the DB sha256 for every
   package, and `populate` checks it again.
3. **Mounts.** `enter` builds the bubblewrap command with `--clearenv` and
   `--unshare-all`. The only host paths it binds are the root (read-only
   unless `--rw`), the work, pkgdest, srcdest and ccache dirs you pass,
   `/dev`, `/proc`, and, with `--gpu`, `/dev/kfd`, `/dev/dri` and `/sys`
   (read-only). With `--net` it also binds `/etc/resolv.conf`.
   `LD_LIBRARY_PATH`, `PYTHONPATH`, `ROCM_PATH`, `HIP_PATH` and
   `CMAKE_PREFIX_PATH` are never passed in.
   `enter` launches the whole bubblewrap command in the host's memory-capped
   `builds.slice`: outside the slice it starts
   `systemd-run --user --scope --slice=builds.slice choom -n 500 -- bwrap …`,
   and inside the slice it adds only `choom -n 500`. Every process in the
   root inherits the cap and the raised OOM score, so an overrun kills a
   compiler and fails the build without touching the launching process. The
   host's makepkg and ninja shims cannot see into the root, which is why the
   launch itself is wrapped. `enter` refuses to start unless `builds.slice` is
   loaded with a finite `MemoryMax`, because `systemd-run --slice=` would
   otherwise create an uncapped slice. This replaces the earlier `SIGSTOP`
   throttle, which paused new jobs but left running compilers holding their
   memory.
4. **Ownership proof.** `populate` and `add` record every package's file list
   under `ROOT/.ashp-root/`. `verify` walks `/opt` and fails when any file is
   unowned, when any `/opt/rocm` file is owned by a non-foundation package,
   when a forbidden repo appears in any source, or when
   `/opt/rocm/.info/version` is not the expected version. It also reads every
   host-architecture ELF file under `/usr/bin`, `/usr/lib` (with Python
   `site-packages`) and `/opt/rocm`, and fails when a `DT_NEEDED` entry does
   not resolve inside the root or a `RUNPATH` names a directory outside the
   root's install tree, unless the committed allowlist covers the finding.
   `probe` maps every
   library that `ldd` resolves for its outputs to the package that owns it,
   following symlinks inside the root. It also fails on unresolved libraries,
   unexpected RUNPATH entries, and host paths embedded in the outputs.

Because `/opt/rocm` inside the root is the same path the host has after W5,
RUNPATHs, CMake exports, `hipconfig` and `.info/version` are correct by
construction, and no PKGBUILD needs a ROCm path parameter. Host builds with
`ROCM_PATH` and similar variables cannot give that guarantee. F's own CMake
configs fall back to `PATHS "/opt/rocm"`, and the W2A PKGBUILDs hard-code
`/opt/rocm` dozens of times, so any miss would silently resolve to 7.13 on the
host.

The root has no pacman local DB, so `.BUILDINFO` has no `installed =` lines.
The provenance record is the lock (`ROOT/.ashp-root/lock.json`) together with
the manifest (`ROOT/.ashp-root/manifest.json`), which lists each package's
name, version, source and file sha256. Keep both next to the packages you
build.

## The W2A flow

The examples use `$WORK` for a scratch directory on a filesystem with room
for about 30 GiB, and `$STAGING` for the directory that holds the
`ashp-w1-staging` repo. Both are local choices; do not commit them.

1. **Create the output repo.** Run
   `c_buildroot.py publish $WORK/repo ashp-w2a` with no packages to write an
   empty `ashp-w2a` DB. `publish` refuses any repo name the host's pacman uses,
   and any directory that a host repo serves through `file://`.
2. **Lock.** Pass the DBs in priority order: staging, then `ashp-w2a`, then the
   host's sync DBs (`/var/lib/pacman/sync/*.db`), with the 7.13 repo as
   `--forbid-db`:

   ```sh
   S=/var/lib/pacman/sync
   tools/c_buildroot.py resolve --out $WORK/lock/torch-chain.json \
     --db ashp-w1-staging=$STAGING/ashp-w1-staging.db.tar.zst \
     --db ashp-w2a=$WORK/repo/ashp-w2a.db.tar.zst \
     --db cachyos-znver4=$S/cachyos-znver4.db --db cachyos-core-znver4=$S/cachyos-core-znver4.db \
     --db cachyos-extra-znver4=$S/cachyos-extra-znver4.db --db cachyos=$S/cachyos.db \
     --db core=$S/core.db --db extra=$S/extra.db \
     --pool ashp-w1-staging=$STAGING --pool ashp-w2a=$WORK/repo --cache $WORK/cache/pkgs \
     --foundation-repo ashp-w1-staging --foundation-repo ashp-w2a \
     --forbid-db strix-halo-gfx1151=$S/strix-halo-gfx1151.db \
     --targets-file tools/buildroot/torch-chain.targets
   ```

   Every userland package is locked at its sync DB version, even when the
   host runs another version. The W2A root models the host after W5, and W5
   is a full `pacman -Syu`, so the host will run the sync DB versions too. The
   host's package cache (`--host-cache`) and the `--cache` dirs are download
   caches only: a file there is used when it is the file the DB names and its
   sha256 matches the DB entry, and it is refused otherwise, even at the same
   version. The host's installed packages decide only which of several
   providers of a dependency is chosen, as `pacman -Syu` would keep it. See
   [the F protobuf and Abseil contract](#f-protobuf-and-abseil-contract-108)
   for the bugs that led to this rule.

   The command exits nonzero while the lock has problems. `missing-file`
   problems are fixed with
   `c_buildroot.py fetch LOCK --dest $WORK/cache/pkgs`. Pass the same dir as
   `--cache` on later re-locks.
3. **Populate.** `c_buildroot.py populate LOCK $WORK/root` extracts the lock
   into a fresh root, then runs `ldconfig` and `update-ca-trust` inside it. It
   also adds a `builder` user with your uid, and it creates the `/build`,
   `/pkgdest`, `/srcdest` and `/ccache` mount points that `enter` binds into
   the read-only root. The torch-chain lock is 423 packages and about 10 GiB,
   and it populates in about a minute.
4. **Verify and probe.** Run
   `c_buildroot.py verify $WORK/root --foundation-repo ashp-w1-staging --foundation-repo ashp-w2a --forbid-repo strix-halo-gfx1151 --expect-rocm 7.14.1`.
   Besides ownership, sources and the ROCm version, `verify` checks linkage
   across the whole root without loading anything. It reads the dynamic
   section of each ELF file under `/usr/bin`, `/usr/lib` and `/opt/rocm`,
   skipping `/usr/lib/debug` and objects for other machines such as AMDGPU
   code objects. It runs two checks on each file:

   - **NEEDED.** It resolves each `DT_NEEDED` entry as `ld.so` would: through
     `DT_RPATH` when there is no `DT_RUNPATH`, then `DT_RUNPATH`, with
     `$ORIGIN` as the object's directory in the root, then the root's
     `/etc/ld.so.cache`, then `/usr/lib`. A candidate counts only if it is an
     ELF file of the same class and machine. The check does not model
     `LD_LIBRARY_PATH`, an `RPATH` inherited from the loading executable, or a
     library that is already loaded by soname, as when a Python extension
     relies on `import torch` having loaded `libc10.so`.
   - **RUNPATH.** Every `DT_RUNPATH` and `DT_RPATH` entry must be under `/usr`
     or `/opt/rocm`, or start with `$ORIGIN`. An entry such as a build or CI
     tree (`/build`, `/__w`, `/startdir`), `/home`, `/tmp`, `/srv` or a
     relative path is a hit. Such a directory is absent on the host at best,
     and at worst it is writable and changes what the object loads.

   The report lists every finding, allowed or not, under `unresolved_needed`
   and `foreign_runpath`, grouped by owning package.
   `tools/buildroot/needed-allow.toml` lists the accepted ones: `[[needed]]`
   and `[[runpath]]` entries, each with the owning package, an fnmatch pattern
   for the object path, the soname or `RUNPATH` entry, a reason and, for a real
   defect, its tracking issue. `verify` fails on any finding that no entry
   covers. It also fails on any entry that covers nothing in the root, because
   the finding was cured or the object is gone, so the list stays minimal.
   Remove a stale entry in the change that cures it. Never allowlist a
   finding that a correct lock or a package fix cures; fix the lock or the
   package instead. `--allowlist PATH` picks another file and
   `--no-allowlist` reports every finding as a violation.

   The committed entries fall into these classes:

   - optional plugins and tools whose provider is an optdepend not in the
     root (VTK modules pulled in by opencv, Qt 6 plugins, the avahi and
     pinentry GTK and Qt frontends, groff's X11 tools, glycin's HEIF loader,
     JACK's FireWire backend, qv4l2, tiffgt, sensord, glibc's memusagestat,
     and the UCX InfiniBand and Open MPI UCC transports);
   - the CUDA-only parts of openucx and Open MPI;
   - the 32-bit compiler-rt runtimes, which need a 32-bit libc;
   - objects only loaded after their importer has loaded the missing
     sonames (torchvision's `image.so`, systemd's `libsystemd-core`);
   - Python's `_tkinter`, whose Tcl/Tk is an optdepend;
   - `/startdir` `RUNPATH` leaks in Arch's boost-libs and sdl3;
   - real defects, tracked so that they do not block W2A: `torch_shm_manager`
     in the W2A PyTorch (#109: a `/build` `RUNPATH` instead of
     `$ORIGIN/../lib`, so `libc10.so` and `libshm.so` do not resolve), and F's
     TheRock objects whose `RUNPATH` names the `/__w` CI tree, so that
     amdsmi, `llvm-omp-kernel-replay`, `xmlwf` and rocprofiler-sdk miss their
     `rocm_sysdeps` or sibling libraries (#108).

   A 584-package root has about 4,000 such
   files and checks in under 20 seconds. Then run `c_buildroot.py probe` with the same repo flags and an empty
   `--work` dir. Re-run both after each change to the root.
5. **Build** one package at a time:

   ```sh
   tools/c_buildroot.py enter $WORK/root --work $PKGDIR --pkgdest $WORK/out \
     --srcdest $WORK/src --ccache $WORK/ccache [--net] [--gpu] -- makepkg -Cf --nodeps
   ```

   `--nodeps` is correct because the root has no pacman local DB; the lock is
   the dependency proof. Fetch sources first, either with `--net` and
   `makepkg --verifysource`, or into the SRCDEST on the host. Pass `--net` to
   the build only when a step needs it, and record why.
6. **Publish and add.** Run `c_buildroot.py publish $WORK/repo ashp-w2a PKG...`,
   then `c_buildroot.py add $WORK/root PKG...`. `add` replaces an older
   version of the same package and deletes the files it no longer ships. It
   refuses to overwrite another package's files. When a W2A build replaces an
   Arch stand-in, such as `python-numpy-gfx1151` replacing `python-numpy`, run
   `c_buildroot.py remove $WORK/root python-numpy` first. For a bigger change,
   re-lock and populate a fresh root.
7. **Smoke** inside the root with `enter --gpu` before anything reaches the
   host. Delete each build tree once its package is in the repo.

## The pinned makepkg.conf

`tools/buildroot/makepkg.conf` follows the host's CachyOS makepkg.conf, with
these deliberate choices:

- **Parallelism defaults to 6 jobs.** This covers `MAKEFLAGS`, `NINJAFLAGS`,
  and the exported `MAX_JOBS`, `CMAKE_BUILD_PARALLEL_LEVEL` and
  `CARGO_BUILD_JOBS`. Builds run in `builds.slice` (32G, no swap), and heavy
  hipcc units such as PyTorch's CK GEMM kernels peak near 4G each. Override it
  per build with `enter --setenv ASHP_BUILD_JOBS=N`: 4 for FlashAttention's CK
  kernels, 8 for TorchVision. Raise a count only after a first run's
  `memory.peak` stays under 20G.
- **ccache is on, with `CCACHE_MAXSIZE=2G`.** `ccache` is therefore a
  torch-chain target. Pass `enter --ccache DIR` to share one cache across
  builds.
- **`INTEGRITY_CHECK=(b2)`**, like the host. The root's packaged
  makepkg.conf uses `sha256`. The setting only affects `makepkg -g`.
- **`PKGDEST` and `SRCDEST` are not set** in the file. `enter --pkgdest` and
  `--srcdest` set them.
- **LTO is on (`-flto=auto`).** Configure scripts that read their test
  objects can misdetect under it. See the
  [LTO Configure Probe Audit](lto-configure-probe-audit.md).

## Probe results

These results are from 2026-09-22, on the torch-chain root. The lock had 423
packages: 48 from `ashp-w1-staging` and the rest host-version userland. It
held nothing from `strix-halo-gfx1151`.

| Probe | Result |
| --- | --- |
| Root identity | `/opt/rocm/.info/version` 7.14.1, `hipconfig --version` 7.14.60850, Python 3.14.7 |
| `verify` | 21,650 files under `/opt` checked, 0 violations |
| hipcc `vadd` on the GPU | `compiled HIP_VERSION=71460850 runtime=71460850 driver=71460850`, `vadd OK` on gfx1151 |
| CMake HIP library | `hip_DIR=/opt/rocm/lib/cmake/hip`. Every `/opt` path in `CMakeHIPCompiler.cmake` is under `/opt/rocm`. `saxpy OK`. |
| makepkg under the pinned conf | `ashp-hip-probe-1-1` built with ccache enabled. The packaged `libsaxpy.so` has `RUNPATH [/opt/rocm/lib]`, and the packaged binary ran on the GPU. |
| Linkage | `ldd` on five outputs resolved 23 libraries, with 0 violations. Every `/opt/rocm` library maps to a 7.14.1-1 package from `ashp-w1-staging`. Every `/usr` library maps to host-version glibc, libgcc or libstdc++. |

## Known gaps

- F has no `magma-gfx1151`. The generation-C torch is built with
  `USE_MAGMA=0`.
- `hipcc-gfx1151` and `hip-runtime-amd-gfx1151` do not depend on
  `hip-gfx1151`, which owns `hip_runtime.h` and `lib/cmake/hip`. This gap
  predates F and was already in 7.13. The torch-chain targets list
  `hip-gfx1151` explicitly.
- vLLM's makedepends bring in `rust`, because `python-setuptools-rust`
  depends on it. The vLLM package disables the Rust extensions
  (`CARGO=/usr/bin/false`, `RUSTUP_AUTO_INSTALL=0`) and fails if the wheel
  contains them. `vllm-build.targets` names the toolchain with a version floor.
  `py-closure.targets` also carries `rust` and the maturin tools; the vLLM root
  does not need that file.
- A bare `rust` target resolves to the host's `rustup`, which provides an
  unversioned `rust` and would download a toolchain at build time. Name the
  target with a version floor (`rust>=1:1.90`) so the real Arch toolchain wins.
- `python-gfx1151`'s `sysconfig` sets `AR=/usr/bin/llvm-ar`, which setuptools
  `build_clib` uses (Pillow), but `python-gfx1151` does not depend on `llvm`.
  The host has `llvm` installed, so only the root shows the gap;
  `py-closure.targets` lists `llvm` for it.
- ONNX: the W2A check is that `torch.onnx` imports in the root. Arch
  `python-onnx` is a host concern at W5 and is not in the W2A targets.
- The maturin wheels (tokenizers, safetensors, watchfiles, pydantic-core) fetch
  crates from crates.io at build time, so they build with `enter --net`.
  Crates are cached under the ccache dir (`CARGO_HOME=/ccache/cargo`).

## W2A model/runtime closure (#110)

On 2026-09-22 the #110 closure was built in the root and published to
`ashp-w2a`. The build root was `torch-chain.targets` plus
`py-closure.targets` (445 packages). The smoke root was `torch-chain.targets`
plus `model-closure.targets` (465 packages), with compressed-tensors and
Accelerate added by `c_buildroot.py add`. `verify` found no violations in
either root.

| Package | Version | Build notes |
| --- | --- | --- |
| `python-numpy-gfx1151` | 2.5.3-1 | OpenBLAS for BLAS and LAPACK, amdclang 23 |
| `python-pyyaml-gfx1151` | 6.0.3-2 | Same source, rebuilt |
| `python-psutil-gfx1151` | 7.2.2-2 | Same source, rebuilt |
| `python-pillow-gfx1151` | 12.3.0-1 | Needed `llvm` in the root (see Known gaps) |
| `python-frozenlist-gfx1151` | 1.8.0-2 | Same source, rebuilt for aiohttp |
| `python-multidict-gfx1151` | 6.9.1-1 | |
| `python-yarl-gfx1151` | 1.25.1-1 | |
| `python-aiohttp-gfx1151` | 3.14.3-1 | System llhttp |
| `python-sentencepiece-gfx1151` | 0.2.2-1 | Offline abseil patch; built with no network |
| `python-tokenizers-gfx1151` | 0.23.2-1 | Built with `--net` for crates |
| `python-safetensors-gfx1151` | 0.8.0-1 | Built with `--net` for crates |
| `python-watchfiles-gfx1151` | 1.3.0-1 | Built with `--net` for crates |
| `python-pydantic-core-gfx1151` | 2.46.5-1 | Built with `--net` for crates; pairs with Arch pydantic 2.13.5 |
| `python-transformers-gfx1151` | 5.16.1-1 | Pure Python |
| `python-mistral-common-gfx1151` | 1.11.7-1 | Pure Python |
| `python-compressed-tensors-gfx1151` | 0.17.0-1 | Pure Python |
| `python-accelerate-gfx1151` | 1.15.0-1 | Pure Python |

The in-root smoke ran under Python 3.14.7 and passed:

- NumPy: OpenBLAS for BLAS and LAPACK, and a linear-algebra check.
- PyYAML: the libyaml loader.
- Pillow: PNG, JPEG, WebP, AVIF, TIFF and JPEG 2000 round trips, plus the
  freetype, lcms, raqm and libimagequant features.
- psutil: memory and process probes.
- tokenizers: BPE training and encoding.
- safetensors: a NumPy round trip.
- Transformers: `transformers.models.gemma4` and a fast tokenizer.
- mistral-common: `ReasoningEffort` and a chat request.
- pydantic 2.13.5 with pydantic-core 2.46.5: model validation.
- aiohttp: the C HTTP parser and a `ClientSession`.
- frozenlist, multidict and yarl: their C extensions loaded.
- sentencepiece: training and a round trip. The extension links no
  sentencepiece, protobuf or abseil library.
- watchfiles and huggingface-hub 1.32.0: import checks.
- Linkage: `ldd` resolved all libraries for all 41 native extensions in the
  root.

compressed-tensors and Accelerate import torch when they load, so their smoke
covers only metadata and bytecode compilation until torch is in `ashp-w2a`.
Nothing here was installed on the host.

## W2A ROCm Triton 3.8 (#109)

On 2026-09-22 `python-triton-gfx1151` 3.8.0+git669b31ac-1 was built in a
fresh `torch-chain.targets` root (423 packages) and published to `ashp-w2a`.

- **Source:** ROCm/triton `release/internal/3.8.x` at `669b31ac`, the pin in
  ROCm PyTorch `13da0862` `.ci/docker/ci_commit_pins/triton.txt`.
- **Carry:** refreshed 0001 (root `pyproject.toml` build requirements) and
  0002 (`-Werror`). The 3.0-era `AttrsDescriptor.__repr__` patch was dropped.
- **LLVM:** the `llvm-5f07f818-ubuntu-x64-1.tar.gz` prebuilt that
  `cmake/llvm-info.json` names, pinned in `source=()` by sha256. The build ran
  with `TRITON_OFFLINE_BUILD=ON` and no network, with `LLVM_SYSPATH` on the
  unpacked tarball and `JSON_SYSPATH=/usr` (Arch nlohmann-json).
- **Build:** about 22 minutes with 14 compile jobs and 2 link jobs
  (`TRITON_PARALLEL_LINK_JOBS`). The build tree peaked at about 5.3 GiB.
- **Linkage:** `libtriton.so` links only libz, libstdc++, libgcc_s, libm and
  libc; LLVM and MLIR are static. The package depends on `libstdc++` and
  `zlib` for that reason.
- **makepkg warning:** `triton/backends/nvidia/lib/gsan.ll`, the NVIDIA GSan
  runtime IR, records its source path under the build root's `/build/src`.
  It is unused on ROCm and carries no host path.

The in-root smoke ran on the gfx1151 GPU (`enter --gpu`). torch is not in the
root yet, and Triton's `GPUDriver` imports torch for device and stream
queries, so the smoke installs a small `torch` shim that answers those queries
through the HIP runtime and allocates buffers with `hipMalloc`. Triton's own
compiler, HIP driver and launcher do the rest:

- `import triton` reports 3.8.0; the distribution version is
  3.8.0+git669b31ac. The backends are `amd` and `nvidia`.
- The active target is `GPUTarget('hip', 'gfx1151', 32)`.
- A `@triton.jit` vector add over 98,432 float32 values compiled through
  TTIR, TTGIR, LLIR, AMDGCN and HSACO for gfx1151 and matched NumPy exactly.
- Triton compiles its HIP launcher with the root's C compiler on first use, so
  a runtime without a C compiler cannot launch kernels. Arch's
  `python-triton` does not declare one either.

`verify` found no violations after the add. Nothing was installed on the host.

## W2A AOTriton 0.13b (#109)

On 2026-09-23 `python-aotriton-gfx1151` 0.13b-1 was built and published to
`ashp-w2a`. The root was re-locked from `torch-chain.targets`, which now
names `python-triton-gfx1151` (424 packages), and repopulated in place.

- **Source:** tag `0.13b` at `6e00ef3e`, with the vendored Triton staged from
  the `db82b800` package source, the same hyperjump commit 0.12b pinned.
- **Carry:** 0001 (gate the vendored Triton's NVIDIA and GSan artifacts) is
  byte-identical to 0.12b. The masked `c44b870b` cherry-pick is gone from the
  renderer template, because that commit is not in the pinned history.
- **Build:** `makepkg -Cf --nodeps` with `--net`, in about 81 minutes. The
  build needs network by design: configure installs `requirements.txt` and the
  `aotriton` code generator into a disposable venv, clones the `ROCm/aiter`
  tag named in `third_party/aiter.txt` (`v0.1.11`) for its kernel sources, and
  the vendored Triton wheel build downloads its own LLVM into `TRITON_HOME`.
  The build has 22,892 ninja steps: the vendored Triton wheel, about 1,960 C++
  shim objects, then about 20,900 gfx1151 kernel images.
- **Memory:** 14 ninja jobs plus the nested Triton build left about 33 GiB
  available. The template now caps the nested Triton's links with
  `TRITON_PARALLEL_LINK_JOBS` (default 2), as the standalone Triton template
  does.
- **Disk:** the build tree peaked at about 16 GiB. 7.2 GiB of that was the
  vendored Triton's downloaded LLVM and NVIDIA toolchains in `TRITON_HOME`,
  which nothing reads once the nested wheel is installed; it was deleted while
  the kernels compiled to stay under the disk cap. Plan for about 16 GiB free
  per AOTriton build.
- **Output:** 137 MB installed: `libaotriton_v2.so.0.13.0`, the
  `pyaotriton` extension in `/usr/lib`, headers, CMake config and the
  `aotriton.images/amd-gfx115x` kernel archives. `libaotriton_v2.so` links
  TheRock's HIP runtime plus `liblzma`, `libstdc++` and `libgcc_s`; the
  package does not yet declare `xz`, and neither does Arch.
- The `.BUILDINFO` step prints an `alpm` initialization error because the root
  has no pacman database. It is cosmetic; the package metadata is complete.

The in-root smoke ran on the gfx1151 GPU (`enter --gpu`) without torch:

- `import pyaotriton` loads `/usr/lib/pyaotriton.cpython-314-x86_64-linux-gnu.so`.
- The v3 `attn_fwd` operator ran on fp16 Q, K and V of shape (2, 4, 256, 64)
  held in `pyaotriton.HipMemory` buffers, non-causal and causal. Both returned
  `hipSuccess` and matched a NumPy float32 reference within 1.1e-3 max
  absolute error.

`verify` found no violations after the add. Nothing was installed on the host.

## W2A ROCm PyTorch 2.12 (#109)

On 2026-09-25 `python-pytorch-opt-rocm-gfx1151` 2.12.0-5 was built, published
to `ashp-w2a`, and added to the root.

- **Source:** ROCm PyTorch `release/2.12` at `13da0862`, with `USE_MAGMA=0` and
  `PYTORCH_ROCM_ARCH=gfx1151`, against the root's ROCm Triton 3.8.0 and
  AOTriton 0.13b.
- **Carry:** 0001-0004 and 0006-0008 are kept. 0005 is refreshed for the CK
  architecture list. 0009, the AOTriton 0.12 lazy-tensor callbacks, is dropped.
  0010 is new: it disables the build's own system AOTriton install.
- **Build:** `makepkg -ef --nodeps --holdver`, with no network, in 64 minutes
  over 7,586 ninja steps. `build()` deliberately rebuilds from a fresh CMake
  state, so an interrupted build restarts from zero, and ccache is disabled.
- **Memory:** it ran inside `builds.slice` (32G cap, no swap) as a detached
  user service under the heavy-work lease, with `ASHP_BUILD_JOBS=6`. The
  service's `memory.peak` was 7.8 GiB, with no OOM events. An earlier attempt
  at 14 jobs, without the slice, drove the host into OOM kills.
- **Output:** a 132 MB package. makepkg warned that some binaries reference
  `$srcdir` (embedded build paths) and that `.BUILDINFO` has no installed-package
  list; the root has no pacman database.
- **Root smoke** (`enter --gpu`): torch 2.12.0 with HIP 7.14.60850;
  `has_magma` is False; the device is gfx1151; a matmul passes; the preferred
  BLAS backend is hipBLASLt (reported as `Cublaslt`) without
  `TORCH_BLAS_PREFER_HIPBLASLT`; `scaled_dot_product_attention` passes; and
  `torch.compile` through Triton passes.

## W2A vLLM build tools (#111)

On 2026-09-25 the vLLM 0.30.0 build tools were added to the root before the
vLLM build, so the root matches the package's makedepends. vLLM's `setup.py`
imports `setuptools_rust`, which imports `semantic_version`, and the package
names both.

- **Targets:** `vllm-build.targets` lists `python-setuptools-rust`,
  `python-semantic-version` and `rust>=1:1.90`.
- **Lock:** `resolve` over `torch-chain.targets` plus `vllm-build.targets`
  produced 434 packages with no problems. Against the root's manifest the lock
  adds seven packages and changes no versions:
  - `python-setuptools-rust` 1.13.0-1 and `python-semantic-version` 2.10.0-9
    (host cache, `extra`);
  - `rust` 1:1.98.1-1.1 (`cachyos-extra-znver4`, from the fetch cache);
  - `compiler-rt`, `lld` and `libgit2`, which `rust` depends on, and `llhttp`
    (host cache, `cachyos-extra-znver4`).
  Each file's sha256 matched its sync DB entry.
- **Add:** `c_buildroot.py add` extracted the seven files with the lock's
  source label for each. The root's W2A builds (PyTorch, TorchVision and
  FlashAttention) stay in place.
- **Checks:** `verify` found 437 packages, 21,875 `/opt` files and no
  violations. Inside the root, `import setuptools_rust, semantic_version`
  reports setuptools-rust 1.13.0 and semantic-version 2.10.0 under Python
  3.14.7.

A fresh vLLM root is `torch-chain.targets`, `model-closure.targets` and
`vllm-build.targets`, with the W2A torch-chain builds added.

## F protobuf and Abseil contract (#108)

MIGraphX 2.16.1 (`migraphx-gfx1151` 7.14.1-1 in F) is linked against Arch
protobuf 36.1 and Abseil 20260817 on purpose. Its package declares
`libprotobuf.so=36.1.0-64` and no Abseil dependency, and protobuf depends on
plain `abseil-cpp`. Abseil has no soname in the package graph, so nothing but
this contract ties the two versions together.

- **Build roots.** `torch-chain.targets` names `protobuf>=36.1` and
  `abseil-cpp>=20260817.0`. The other targets files are always resolved with
  it, so they need no pins of their own.
- **Resolver fix.** `resolve` used to lock a userland package at the
  host's installed version when that file was in the host cache. Each rule
  that tried to keep such a mixed lock consistent left a hole:
  - Checking a host file against the sync DB entry's provides let a host
    protobuf 35.1 pass for `libprotobuf.so=36.1.0-64`. The lock recorded
    protobuf 35.1 under the 36.1 file name with no sync-DB sha256, and Abseil
    stayed at the host's 20260526.
  - Judging a host file by its own provides moved protobuf to 36.1 and Abseil
    to 20260817, but left their consumers at the host versions:
    python-protobuf 35.1 with `depend = protobuf=35.1`, and re2, python-grpcio
    and python-grpcio-tools linked against `libabsl_*.so.2605.0.0`, which
    Abseil 20260817 does not ship. `import grpc` failed in that root.
  - Substituting a host file only while its dependency cone was unchanged
    fixed those, and moved about 115 Python packages to their sync DB
    versions because the foundation's `python-gfx1151` 3.14.7 is newer than
    the host's 3.14.6. It missed the reverse direction: a package that moved
    to its sync DB version kept a host-version dependency whose soname it no
    longer links. ffmpeg 9.0.2 needs `libbluray.so.4`, and the host's
    libbluray 1.4.1 ships `.so.3`; opencv 5.0.0-12 needs
    `libOpenEXR-3_5.so.34`, and the host's openexr 3.4.14 ships 3.4.

  `resolve` now locks every userland package at its sync DB version and uses
  the host cache only as a download cache (see [the W2A flow](#the-w2a-flow),
  step 2). The W2A root models the host after W5, and W5 is a full
  `pacman -Syu`, so no host version belongs in it. On 2026-09-25 the re-lock
  moved libbluray to 1.5.1, openexr to 3.5.0, imath to 3.2.3 and gtest to
  1.18.0, which also cures Abseil 20260817's test helpers that link
  `libgtest.so.1.18.0`. An overlay of the re-lock's 87 changed packages on the
  existing root passed `verify` with the committed allowlist.
- **Existing W2A root.** A root populated before the fix holds protobuf 35.1
  and Abseil 20260526. Before the torch-migraphx smokes are re-run, re-lock the
  root with the fixed tool and the pinned targets, `fetch` the new files,
  `populate` a fresh root, and `add` the W2A-built packages back into it.
- **Host at W5.** The host moves to protobuf 36.1 and Abseil 20260817 in the
  W5 transaction, through a full `pacman -Syu`. Never install F or protobuf
  with a partial `pacman -U`: pacman tracks the protobuf soname, but not the
  Abseil version, so a partial update can leave a protobuf 36.1 that needs
  Abseil 20260817 on top of an older Abseil.

## W2A vLLM runtime closure (#110, #111)

On 2026-09-25 the Arch runtime closure for vLLM 0.30.0 was added to the root,
so that the vLLM package can be imported and served there once it is built.
Before the change, `importlib.util.find_spec` in the root found only 16 of 87
import names: those of vLLM 0.30.0 `requirements/common.txt` and
`requirements/rocm.txt`, and of the package's other ASHP depends. The root held
build tools only.

- **Targets:** `vllm-build.targets` now lists the Arch packages that
  `python-vllm-rocm-gfx1151` depends on, the `common.txt` entries that Arch
  packages but the depends do not name yet, and `python-poetry-core`, which
  builds `python-prometheus-fastapi-instrumentator-gfx1151`.
  `model-closure.targets` now names `python-compressed-tensors-gfx1151`,
  because torch is in `ashp-w2a`.
- **Lock:** `resolve` over `torch-chain.targets`, `model-closure.targets` and
  `vllm-build.targets` produced 580 packages. Against the root's manifest it
  adds 145 packages and changes no versions. The W2A builds that were added
  by hand (TorchVision, TorchAO, Torch-MIGraphX and FlashAttention) are not in
  the lock and stay in the root. Three OpenTelemetry exporter files were not
  in the host cache; `fetch` downloaded them, and every added file's sha256
  matched its sync DB entry.
- **Add:** 133 host-cache or sync-DB packages, and 12 `ashp-w2a` closure
  builds (Transformers, tokenizers, safetensors, mistral-common, pydantic-core,
  aiohttp with frozenlist, multidict and yarl, sentencepiece, watchfiles and
  compressed-tensors), each with its lock source label. Arch `python-opencv` brings in Qt 6, VTK and Open MPI.
- **Checks:** `verify` found 584 packages and no violations. Inside the root,
  FastAPI, Starlette, uvicorn, OpenAI, pydantic with pydantic-core 2.46.5,
  Transformers, tokenizers, safetensors, mistral-common, OpenCV, pyzmq, regex,
  tiktoken, protobuf, huggingface-hub, compressed-tensors and the
  OpenTelemetry SDK import without a GPU.

Still missing from the root, and not Arch packages:

- W2A rebuilds of existing ASHP packages: `python-uvloop-gfx1151`,
  `python-httptools-gfx1151`, `python-msgspec-gfx1151` and
  `python-openai-harmony-gfx1151`, which are vLLM depends, and the new
  `python-prometheus-fastapi-instrumentator-gfx1151`. The lease job below
  builds them.
- vLLM depends that no sync DB carries: einops, py-cpuinfo and pybase64. The
  host has them from AUR or an older Arch build. The lease job builds them
  as `-gfx1151` lanes.
- `xgrammar` and its runtime dependency `apache-tvm-ffi`: vLLM imports
  xgrammar in every process. The lease job builds both as `-gfx1151` lanes.
- `common.txt` entries with no Arch or ASHP package, none of them on the
  required runtime set: `depyf`, `anthropic`, `lm-format-enforcer`,
  `outlines_core`, `fastapi-cli`, `model-hosting-container-standards`,
  `opentelemetry-semantic-conventions-ai`, and the tracked #110 gaps `mcp`
  (Arch has 1.29.0) and `llguidance`.
- Arch cannot meet these exact pins: `lark ==1.2.2` (Arch
  `python-lark-parser` 1.3.1 is in the root), `numba ==0.65.0` and
  `grpcio ==1.78.0` (the root has grpcio 1.83.0 through OpenTelemetry).
- The `rocm.txt` feature and test extras are not in the root: `datasets`,
  `peft`, `pytest-asyncio`, `tensorizer`, `runai-model-streamer`,
  `conch-triton-kernels`, `timm`, `amd-quark`, `tilelang`,
  `fastsafetensors`, `mooncake-transfer-engine-rocm` and
  `grpcio-reflection`.
- The pip `ninja` module; the Arch `ninja` binary is in the root.

## W2A vLLM lease job closure (#110, #111)

On 2026-09-25 the vLLM 0.30.0 runtime set was audited against `ced6857a`
with the 0016 carry applied. The set required before w2a-validate is what
`vllm serve` imports at module level before it serves a request, plus the
imports on the request paths the W2A scenarios exercise. The small closure
packages are built in the vLLM lease job, leaves first, and each is published
to `ashp-w2a` and added to the root before the next one.

- **Rebuilds:** `python-uvloop-gfx1151` 0.22.1, `python-httptools-gfx1151`
  0.8.0, `python-msgspec-gfx1151` 0.21.1 and
  `python-openai-harmony-gfx1151` 0.0.8 are already at the latest PyPI
  releases, and no candidate selects a newer one, so each gets pkgrel 2 with
  the source unchanged.
- **New lanes:** `python-einops-gfx1151` 0.8.2 and
  `python-py-cpuinfo-gfx1151` 9.0.0 are pure Python.
  `python-pybase64-gfx1151` 1.5.0 builds its C extension and the bundled
  libbase64 with cmake, and sets `CIBUILDWHEEL=1` so the build fails instead
  of shipping the pure-Python fallback.
- **xgrammar:** `vllm/parser/__init__.py` imports `vllm/parser/harmony.py`,
  which imports xgrammar at module level, and the engine core, the offline
  `LLM` and the API server all reach `vllm.parser`. `python-xgrammar-gfx1151`
  0.2.3 is the version vLLM's CUDA and CPU CI locks test (the ROCm lock tests
  0.2.1), and it ships CPython 3.14 wheels. xgrammar 0.2.3 needs
  apache-tvm-ffi >=0.1.9 to build and to import, and vLLM's `rocm.txt` pins
  apache-tvm-ffi ==0.1.10, so `python-apache-tvm-ffi-gfx1151` is 0.1.10.
  Both are scikit-build-core CMake builds with no CUDA: tvm-ffi compiles 23
  C++ sources, the bundled libbacktrace (33 C files) and one Cython module;
  xgrammar compiles 22 C++ sources and its TVM-FFI bindings, with
  cpptrace and the C++ tests off. Expect a few minutes of CPU time for
  tvm-ffi and about 5-10 minutes for xgrammar.
- **SageMaker:** the 0016 carry makes the model-hosting-container-standards
  import optional in `serve/sagemaker/api_router.py` and
  `serve/lora/api_router.py`, so `vllm serve` starts without it and skips the
  SageMaker-specific and runtime LoRA update routes. It is a #110 gap, not a
  lane; packaging it would pull in the supervisor daemon.
- **Targets:** `vllm-build.targets` adds the lease job's build tools
  (`cython`, `libuv`, `llhttp`, `nasm`, `python-maturin`,
  `python-hatchling` and `python-scikit-build-core`). The root must be
  re-locked and repopulated from the three targets files before the job.
- **Scenario runner:** `tools/inference/runner.py` runs `ps` before each
  vLLM scenario to find stale engine cores, and neither base-devel nor the
  vLLM closure pulls in procps-ng, so `vllm-build.targets` names it. A
  2026-09-25 resolve of the three targets files against the v3 lock inputs
  added only `procps-ng` (from `cachyos-core-znver4`) and changed no versions;
  its files clash with nothing in the root, so a live root takes it through
  `fetch` and `add` instead of a repopulate.
- **openai-harmony:** the rust-wheel template keeps `CARGO_HOME` under
  `$srcdir/.cargo`, which overrides the `CARGO_HOME=/ccache/cargo` that
  `w2a-build.sh` passes, and sets `RUSTUP_AUTO_INSTALL=0`. maturin fetches
  crates during `build()`, so the build needs `net`.

Build order, with `W2A_REPO` pointing at a checkout that has these package
directories (`w2a-build.sh` defaults to an older W2A worktree):

```sh
w2a-build.sh python-py-cpuinfo-gfx1151 2
w2a-build.sh python-einops-gfx1151 2
w2a-build.sh python-prometheus-fastapi-instrumentator-gfx1151 2
w2a-build.sh python-msgspec-gfx1151 6
w2a-build.sh python-httptools-gfx1151 6
w2a-build.sh python-uvloop-gfx1151 6
w2a-build.sh python-pybase64-gfx1151 6
w2a-build.sh python-openai-harmony-gfx1151 6 net
w2a-build.sh python-apache-tvm-ffi-gfx1151 6
w2a-build.sh python-xgrammar-gfx1151 6
w2a-build.sh python-vllm-rocm-gfx1151 6 net
```

- The three pure-Python wheels compile nothing, so 2 jobs is enough, and they
  need no network after the fetch step.
- msgspec, httptools, uvloop and pybase64 each compile a few C files; 6 is
  the root's default and stays far below the slice cap.
- openai-harmony needs `net` for its crates. Its rustc jobs follow
  `ASHP_BUILD_JOBS` through `CARGO_BUILD_JOBS`.
- apache-tvm-ffi and xgrammar each compile a few dozen C and C++ files, so 6
  jobs is enough; scikit-build-core's `cmake --build` follows
  `CMAKE_BUILD_PARALLEL_LEVEL`, which the root's `makepkg.conf` sets from
  `ASHP_BUILD_JOBS`. Neither needs `net`: the sdists carry dlpack,
  libbacktrace and picojson, and the only fetching submodule builds
  (googletest, cpptrace) stay off. tvm-ffi goes first because xgrammar's
  CMake finds tvm_ffi through the installed Python package.
- `python-apache-tvm-ffi-gfx1151` 0.1.10-1 shipped a libbacktrace without an
  ELF reader (LTO hid ELF from its configure probe), which crashed and then
  deadlocked on the first raised TVM-FFI error and hung xgrammar's stub
  generation. 0.1.10-2 compiles that C code without LTO and turns off the
  segfault backtrace handler; its README has the details. Before building
  xgrammar, check inside the root that
  `timeout 60 python -c "import tvm_ffi.core as c; print(c._object_type_key_to_index('no.such.Key'))"`
  prints promptly instead of hanging.
- vLLM needs `net` because its ROCm CMake build fetches `triton_kernels`
  through FetchContent. 6 jobs matches the PyTorch build, whose peak was
  7.8 GiB.
- The other leaves do not depend on each other, so their order only puts the
  cheap builds first. vLLM goes last so that the root holds its whole runtime
  set when it is smoked.

CPU drive prerequisite: importing `vllm.platforms.rocm` without a GPU calls
`torch.cuda.get_device_properties("cuda")` (`vllm/platforms/rocm.py`, when
amdsmi finds no device), so a GPU-less import drive of the ROCm branches needs
a fake-ROCm shim first. Replace `torch.cuda.get_device_properties` with a
function that returns an object with `gcnArchName="gfx1151"`, `major=11`,
`minor=5`, a `name` and `total_memory`, then set
`vllm.platforms.current_platform = RocmPlatform()`. Run the drive once without
the shim, where the platform stays unspecified, and once with it.
