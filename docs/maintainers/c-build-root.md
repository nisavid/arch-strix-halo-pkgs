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
| `torch-chain.targets` | Targets for the torch-chain root (base-devel, build tools, F and the torch makedepends). |
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
2. **Files.** Foundation packages come from their repo pools. Other userland
   uses the host's installed version when that exact file is still in the
   package cache, so the root's glibc and gcc match the host that will run the
   result. Anything else comes from the file the sync DB names. `fetch`
   downloads missing files from the host's configured mirrors and accepts a
   file only when its sha256 matches the sync DB. `populate` checks the DB
   sha256 again for every file that has one.
3. **Mounts.** `enter` builds the bubblewrap command with `--clearenv` and
   `--unshare-all`. The only host paths it binds are the root (read-only
   unless `--rw`), the work, pkgdest, srcdest and ccache dirs you pass,
   `/dev`, `/proc`, and, with `--gpu`, `/dev/kfd`, `/dev/dri` and `/sys`
   (read-only). With `--net` it also binds `/etc/resolv.conf`.
   `LD_LIBRARY_PATH`, `PYTHONPATH`, `ROCM_PATH`, `HIP_PATH` and
   `CMAKE_PREFIX_PATH` are never passed in.
4. **Ownership proof.** `populate` and `add` record every package's file list
   under `ROOT/.ashp-root/`. `verify` walks `/opt` and fails when any file is
   unowned, when any `/opt/rocm` file is owned by a non-foundation package,
   when a forbidden repo appears in any source, or when
   `/opt/rocm/.info/version` is not the expected version. `probe` maps every
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

   The command exits nonzero while the lock has problems. `missing-file`
   problems are fixed with
   `c_buildroot.py fetch LOCK --dest $WORK/cache/pkgs`. Pass the same dir as
   `--cache` on later re-locks.
3. **Populate.** `c_buildroot.py populate LOCK $WORK/root` extracts the lock
   into a fresh root, then runs `ldconfig` and `update-ca-trust` inside it. It
   also adds a `builder` user with your uid. The torch-chain lock is 423
   packages and about 10 GiB, and it populates in about a minute.
4. **Verify and probe.** Run
   `c_buildroot.py verify $WORK/root --foundation-repo ashp-w1-staging --foundation-repo ashp-w2a --forbid-repo strix-halo-gfx1151 --expect-rocm 7.14.1`.
   Then run `c_buildroot.py probe` with the same repo flags and an empty
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

- **Parallelism is 14 jobs.** This covers `MAKEFLAGS`, `NINJAFLAGS`, and the
  exported `MAX_JOBS` and `CMAKE_BUILD_PARALLEL_LEVEL`. The host keeps large
  models resident and has about 37 GiB free, and hipcc at `-j32` is
  OOM-killed.
- **ccache is on, with `CCACHE_MAXSIZE=2G`.** `ccache` is therefore a
  torch-chain target. Pass `enter --ccache DIR` to share one cache across
  builds.
- **`INTEGRITY_CHECK=(b2)`**, like the host. The root's packaged
  makepkg.conf uses `sha256`. The setting only affects `makepkg -g`.
- **`PKGDEST` and `SRCDEST` are not set** in the file. `enter --pkgdest` and
  `--srcdest` set them.

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

- `torch-chain.targets` still uses the Arch `python-numpy`, `python-yaml` and
  `python-pillow` as stand-ins. Replace them with the gfx1151 builds once
  those are in `ashp-w2a`.
- F has no `magma-gfx1151`. The generation-C torch is built with
  `USE_MAGMA=0`.
- `hipcc-gfx1151` and `hip-runtime-amd-gfx1151` do not depend on
  `hip-gfx1151`, which owns `hip_runtime.h` and `lib/cmake/hip`. This gap
  predates F and was already in 7.13. The torch-chain targets list
  `hip-gfx1151` explicitly.
- vLLM's makedepends bring in `rust`, because `python-setuptools-rust`
  depends on it. The vLLM step must either fetch crates explicitly or disable
  the Rust extensions, and its checks must assert which choice was made.
