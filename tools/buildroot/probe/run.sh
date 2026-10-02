#!/usr/bin/env bash
# No-leak probe, run inside the build root by `c_buildroot.py probe`.
# Builds a hipcc program, a CMake HIP library and a makepkg package, runs them
# on the GPU, and prints readelf/ldd for every output so the host side can map
# each resolved library to the root package that owns it.
set -euo pipefail
cd /build

echo "## mounts inside the root"
awk '{print $5}' /proc/self/mountinfo | sort -u
echo "## /opt/rocm/.info/version: $(cat /opt/rocm/.info/version); hipconfig --version: $(hipconfig --version)"
echo "## python: $(python3 --version 2>&1)"

mkdir -p hello
hipcc --offload-arch=gfx1151 -O2 -o hello/hello hello.hip

cmake -S cmake -B cmakelib/build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/build/cmakelib/prefix \
  -DCMAKE_HIP_COMPILER=/opt/rocm/lib/llvm/bin/clang++ | grep -E 'hip_DIR|CMAKE_HIP_COMPILER'
cmake --build cmakelib/build >/dev/null
cmake --install cmakelib/build >/dev/null

echo "## run"
./hello/hello
./cmakelib/prefix/bin/saxpy_probe

echo "## makepkg"
if ! (cd pkg && PKGDEST=/build/pkg makepkg -Cf --nodeps >makepkg.log 2>&1); then
  tail -40 pkg/makepkg.log
  exit 1
fi
grep -E 'ccache|MAX_JOBS|INTEGRITY' pkg/makepkg.log || true
mkdir -p pkgx
bsdtar -xf pkg/ashp-hip-probe-*.pkg.tar.zst -C pkgx
./pkgx/usr/bin/saxpy_probe

for f in hello/hello cmakelib/prefix/lib/libsaxpy.so cmakelib/prefix/bin/saxpy_probe \
         pkgx/usr/lib/libsaxpy.so pkgx/usr/bin/saxpy_probe; do
  echo "## readelf $f"
  readelf -d "$f" | grep -E 'NEEDED|RUNPATH|RPATH' || true
  echo "## ldd $f"
  ldd "$f"
done
echo "## cmake HIP compiler record"
grep -hoE '"/(opt|usr)/[^"]*"' cmakelib/build/CMakeFiles/*/CMakeHIPCompiler.cmake | sort -u | head -20
