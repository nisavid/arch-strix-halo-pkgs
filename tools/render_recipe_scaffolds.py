#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

from compute_recipe_version import compute_version

try:
    import yaml
except ImportError:  # pragma: no cover - fallback path is tested via CLI failure message
    yaml = None


def load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_recipe_manifest(recipe_dir: Path) -> dict:
    manifest = recipe_dir / "vllm-packages.yaml"
    if yaml is None:
        print("RECIPE_MANIFEST_LOAD_FAILED: PyYAML is not installed", file=sys.stderr)
        print("HINT: install python-yaml/PyYAML before running tools/render_recipe_scaffolds.py.", file=sys.stderr)
        raise SystemExit(2)
    with manifest.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render hand-maintained package scaffolds from the recipe manifest")
    parser.add_argument("--recipe-root", required=True, help="git repo root containing the recipe")
    parser.add_argument("--recipe-subdir", default="strix-halo", help="path within the recipe repo")
    parser.add_argument("--policy", default="policies/recipe-packages.toml", help="policy file relative to the packaging repo root")
    parser.add_argument("--output-root", default="packages", help="package output root relative to the packaging repo root")
    parser.add_argument("--only", action="append", default=[], help="render only the named package(s)")
    return parser.parse_args()


def bash_array(items: list[str]) -> str:
    if not items:
        return "()"
    quoted = " ".join(shlex.quote(item) for item in items)
    return f"({quoted})"


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def compiler_env_snippet(compiler_root: str) -> str:
    return textwrap.dedent(
        """\
_setup_compiler_env() {
  local _compiler_root="__COMPILER_ROOT__"
  local _ccache_dir="$srcdir/.ccache/bin"
  if command -v ccache >/dev/null 2>&1; then
    mkdir -p "${_ccache_dir}"
    local _ccache_bin _name
    _ccache_bin="$(command -v ccache)"
    for _name in clang clang++ clang-22 amdclang amdclang++ hipcc hipcc.pl gcc g++ cc c++; do
      ln -sf "${_ccache_bin}" "${_ccache_dir}/${_name}"
    done
    export PATH="${_ccache_dir}:$PATH"
    export CCACHE_BASEDIR="${CCACHE_BASEDIR:-$srcdir}"
    export CCACHE_NOCPP2=1
    export CCACHE_PATH="${_compiler_root}:/opt/rocm/bin:/usr/bin"
    export CC=amdclang
    export CXX=amdclang++
  else
    export CC="${_compiler_root}/amdclang"
    export CXX="${_compiler_root}/amdclang++"
  fi
}

""".replace("__COMPILER_ROOT__", compiler_root)
    )


def render_source_refs(policy_pkg: dict, recipe_pkg: dict) -> tuple[str, str]:
    template = policy_pkg["template"]
    if template == "meta-package":
        return bash_array([]), bash_array([])
    extra_sources = policy_pkg.get("extra_sources", [])
    extra_sha256sums = policy_pkg.get("extra_sha256sums", ["SKIP"] * len(extra_sources))
    if len(extra_sha256sums) != len(extra_sources):
        print("EXTRA_SOURCE_MISMATCH: extra_sources and extra_sha256sums lengths differ", file=sys.stderr)
        print("HINT: add one checksum entry per extra source in policies/recipe-packages.toml.", file=sys.stderr)
        raise SystemExit(2)
    source_refs = policy_pkg.get("source_refs")
    if source_refs:
        sha256sums = policy_pkg.get("sha256sums", ["SKIP"] * len(source_refs))
        if len(sha256sums) != len(source_refs):
            print("SOURCE_REF_MISMATCH: source_refs and sha256sums lengths differ", file=sys.stderr)
            print("HINT: add one checksum entry per source ref in policies/recipe-packages.toml.", file=sys.stderr)
            raise SystemExit(2)
        return bash_array(source_refs + extra_sources), bash_array(sha256sums + extra_sha256sums)

    source_type = policy_pkg.get("source_type", "")
    if template in {"rust-wheel-pypi", "native-wheel-pypi"}:
        pypi_name = policy_pkg["pypi_name"]
        upstream_version = policy_pkg["upstream_version"]
        source_ref = f"https://files.pythonhosted.org/packages/source/{pypi_name[0]}/{pypi_name}/{pypi_name}-{upstream_version}.tar.gz"
    elif source_type == "tarball":
        source_ref = policy_pkg["source_url"]
    else:
        source_ref = f"{policy_pkg['src_subdir']}::git+{recipe_pkg['repo']}"
        branch = recipe_pkg.get("branch")
        if branch:
            source_ref = f"{source_ref}#branch={branch}"
    return bash_array([source_ref] + extra_sources), bash_array(["SKIP"] + extra_sha256sums)


def slugify_step(step: int) -> str:
    return f"step-{step}"


def render_patch_prepare(recipe_pkg: dict) -> str:
    lines: list[str] = []
    for patch in recipe_pkg.get("patches", []):
        patch_type = patch.get("type")
        if patch_type != "sed":
            if patch_type == "patchelf_rpath":
                continue
            print(f"UNSUPPORTED_PATCH_TYPE: {patch_type}", file=sys.stderr)
            print("HINT: extend render_recipe_scaffolds.py to translate this patch type into PKGBUILD logic.", file=sys.stderr)
            raise SystemExit(2)
        file_name = patch["file"]
        marker = patch.get("marker")
        sed_command = patch["sed_command"]
        marker_absent = bool(patch.get("marker_absent"))
        predicate = (
            f"! grep -Fq {shell_quote(marker)} {shell_quote(file_name)}"
            if marker_absent and marker
            else f"grep -Fq {shell_quote(marker)} {shell_quote(file_name)}"
            if marker
            else "true"
        )
        lines.extend(
            [
                f"  # {patch.get('description', patch_type)}",
                f"  if {predicate}; then",
                f"    sed -i {shell_quote(sed_command)} {shell_quote(file_name)}",
                "  fi",
            ]
        )
    return "\n".join(lines)


def sibling_package_upstream_revision(package_name: str) -> str:
    packaging_root = Path(__file__).resolve().parents[1]
    recipe_json = packaging_root / "packages" / package_name / "recipe.json"
    if not recipe_json.exists():
        return "unknown"
    try:
        payload = json.loads(recipe_json.read_text(encoding="utf-8"))
        pkgver = str(payload.get("pkgver", ""))
    except Exception:
        return "unknown"
    return pkgver.split(".", 1)[0] if pkgver else "unknown"


def preserved_pkgrel(package_name: str, version: str) -> int:
    packaging_root = Path(__file__).resolve().parents[1]
    pkgbuild = packaging_root / "packages" / package_name / "PKGBUILD"
    if not pkgbuild.exists():
        return 1
    try:
        content = pkgbuild.read_text(encoding="utf-8")
    except OSError:
        return 1
    pkgver_match = re.search(r"^pkgver=(.+)$", content, re.MULTILINE)
    pkgrel_match = re.search(r"^pkgrel=(\d+)$", content, re.MULTILINE)
    if not pkgver_match or not pkgrel_match:
        return 1
    if pkgver_match.group(1).strip() != version:
        return 1
    return int(pkgrel_match.group(1))


def lemonade_llamacpp_env_lines() -> list[str]:
    hip_rev = sibling_package_upstream_revision("llama.cpp-hip-gfx1151")
    vulkan_rev = sibling_package_upstream_revision("llama.cpp-vulkan-gfx1151")
    return [
        "LEMONADE_LLAMACPP_ROCM_BIN=/usr/bin/llama-server-hip-gfx1151",
        "LEMONADE_LLAMACPP_VULKAN_BIN=/usr/bin/llama-server-vulkan-gfx1151",
        f"LEMONADE_LLAMACPP_ROCM_LABEL=System llama-server-hip-gfx1151 llama.cpp {hip_rev}",
        f"LEMONADE_LLAMACPP_VULKAN_LABEL=System llama-server-vulkan-gfx1151 llama.cpp {vulkan_rev}",
    ]


def render_method_body(package_name: str, policy_pkg: dict, recipe_pkg: dict) -> tuple[str, str, str]:
    template = policy_pkg["template"]
    src_subdir = policy_pkg["src_subdir"]
    install_prefix = policy_pkg.get("install_prefix", "/usr")
    compiler_root = "/opt/rocm/lib/llvm/bin"
    prepare_lines = []
    post_package_lines = []

    if template == "cmake":
        build_body = f"""\
build() {{
  cd "$srcdir/{src_subdir}"

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  local amdclang="$CC"
  local amdclangxx="$CXX"
  local aocl_cflags="-O3 -march=native -mprefer-vector-width=512 -mavx512f -mavx512dq -mavx512vl -mavx512bw -Wno-error=unused-command-line-argument"

  cmake -B build -GNinja . \\
    -DCMAKE_C_COMPILER="${{amdclang}}" \\
    -DCMAKE_CXX_COMPILER="${{amdclangxx}}" \\
    -DCMAKE_C_FLAGS="${{aocl_cflags}}" \\
    -DCMAKE_CXX_FLAGS="${{aocl_cflags}}" \\
    -DCMAKE_C_FLAGS_RELEASE="-DNDEBUG ${{aocl_cflags}}" \\
    -DCMAKE_CXX_FLAGS_RELEASE="-DNDEBUG ${{aocl_cflags}}" \\
    -DCMAKE_BUILD_TYPE=Release \\
    -DCMAKE_INSTALL_PREFIX="{install_prefix}" \\
    -DCMAKE_CXX_CLANG_TIDY=/bin/true

  cmake --build build
}}

package() {{
  cd "$srcdir/{src_subdir}"
  DESTDIR="$pkgdir" cmake --install build
}}"""
    elif template == "llama-cpp":
        if package_name.endswith("-hip-gfx1151"):
            backend = "hip"
        elif package_name.endswith("-vulkan-gfx1151"):
            backend = "vulkan"
        else:
            print(f"UNSUPPORTED_LLAMACPP_PACKAGE: {package_name}", file=sys.stderr)
            print("HINT: llama-cpp renderer currently supports only -hip-gfx1151 and -vulkan-gfx1151 package suffixes.", file=sys.stderr)
            raise SystemExit(2)
        install_root = f"/opt/{package_name}"
        backend_cflags = {
            "hip": "-O3 -march=native -flto=thin -mprefer-vector-width=512 -famd-opt -Wno-error=unused-command-line-argument",
            "vulkan": "-O3 -march=native -flto=thin -mprefer-vector-width=512 -Wno-error=unused-command-line-argument",
        }[backend]
        backend_specific_flags = {
            "hip": [
                "-DGGML_HIP=ON",
                "-DGGML_VULKAN=OFF",
                "-DAMDGPU_TARGETS=gfx1151",
                "-DCMAKE_HIP_COMPILER=${amdclangxx}",
                '"-DCMAKE_HIP_FLAGS=--offload-arch=gfx1151 -mllvm -amdgpu-function-calls=false -mllvm -amdgpu-early-inline-all=true -famd-opt ${_debug_map}"',
                '"-DCMAKE_EXE_LINKER_FLAGS=${_linker_flags}"',
                '"-DCMAKE_SHARED_LINKER_FLAGS=${_linker_flags}"',
                "-DLLAMA_BUILD_SERVER=ON",
                "-DLLAMA_BUILD_TOOLS=ON",
                "-DLLAMA_BUILD_TESTS=OFF",
                "-DLLAMA_BUILD_EXAMPLES=OFF",
            ],
            "vulkan": [
                "-DGGML_HIP=OFF",
                "-DGGML_VULKAN=ON",
                '"-DCMAKE_EXE_LINKER_FLAGS=${_linker_flags}"',
                '"-DCMAKE_SHARED_LINKER_FLAGS=${_linker_flags}"',
                "-DLLAMA_BUILD_SERVER=ON",
                "-DLLAMA_BUILD_TOOLS=ON",
                "-DLLAMA_BUILD_TESTS=OFF",
                "-DLLAMA_BUILD_EXAMPLES=OFF",
            ],
        }[backend]
        cmake_flag_lines = "\n".join(
            [
                "    " + flag + (" \\" if idx < len(backend_specific_flags) - 1 else "")
                for idx, flag in enumerate(backend_specific_flags)
            ]
        )
        build_body = f"""\
build() {{
  cd "$srcdir/{src_subdir}"

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  local amdclang="$CC"
  local amdclangxx="$CXX"
  local build_root="$srcdir/build-{backend}"
  local install_root="{install_root}"
  local backend_cflags="{backend_cflags}"
  local _debug_prefix="/usr/src/debug/{package_name}"
  local _debug_map="-ffile-prefix-map=$srcdir=${{_debug_prefix}}"
  local _linker_flags="-flto=thin -fuse-ld=lld"
  backend_cflags="${{backend_cflags}} ${{_debug_map}}"
  if [[ "{backend}" == "hip" ]]; then
    local _probe_src="$srcdir/.llama-hip-flag-probe.c"
    local _probe_obj="$srcdir/.llama-hip-flag-probe.o"
    local _aggressive_flags="-mllvm -polly -mllvm -polly-vectorizer=stripmine -mllvm -inline-threshold=600 -mllvm -unroll-threshold=150"
    printf '%s\n' 'int main(void) {{ return 0; }}' > "${{_probe_src}}"
    if "${{amdclang}}" -O2 -x c -c "${{_probe_src}}" -o "${{_probe_obj}}" ${{_aggressive_flags}} >/dev/null 2>&1; then
      backend_cflags="${{backend_cflags}} ${{_aggressive_flags}}"
    fi
    rm -f "${{_probe_src}}" "${{_probe_obj}}"
  fi

  rm -rf "${{build_root}}"

  cmake -B "${{build_root}}" -GNinja . \\
    -DCMAKE_C_COMPILER="${{amdclang}}" \\
    -DCMAKE_CXX_COMPILER="${{amdclangxx}}" \\
    -DCMAKE_C_FLAGS="${{backend_cflags}}" \\
    -DCMAKE_CXX_FLAGS="${{backend_cflags}}" \\
    -DCMAKE_C_FLAGS_RELEASE="-DNDEBUG ${{backend_cflags}}" \\
    -DCMAKE_CXX_FLAGS_RELEASE="-DNDEBUG ${{backend_cflags}}" \\
    -DCMAKE_BUILD_TYPE=Release \\
    -DCMAKE_INSTALL_PREFIX="${{install_root}}" \\
    -DCMAKE_CXX_CLANG_TIDY=/bin/true \\
{cmake_flag_lines}

  cmake --build "${{build_root}}"
}}

package() {{
  cd "$srcdir/{src_subdir}"
  local build_root="$srcdir/build-{backend}"
  local install_root="{install_root}"

  DESTDIR="$pkgdir" cmake --install "${{build_root}}"
  rm -f "$pkgdir${install_root}/bin"/test-*
  if command -v patchelf >/dev/null 2>&1; then
    local _bin _libdir
    _libdir="{install_root}/lib"
    for _bin in "$pkgdir{install_root}/bin"/*; do
      [[ -f "${{_bin}}" ]] || continue
      patchelf --set-rpath "$_libdir" "${{_bin}}" 2>/dev/null || true
    done
  fi
  if [[ -d "$pkgdir{install_root}/bin" ]]; then
    local _backend_suffix="{backend}-gfx1151"
    local _tool _base
    for _tool in "$pkgdir{install_root}/bin"/*; do
      [[ -f "${{_tool}}" ]] || continue
      _base="$(basename "${{_tool}}")"
      install -Dm755 /dev/stdin "$pkgdir/usr/bin/${{_base}}-${{_backend_suffix}}" <<EOF
#!/usr/bin/env bash
exec {install_root}/bin/${{_base}} "\\$@"
EOF
    done
  fi
  install -Dm644 "$srcdir/{src_subdir}/LICENSE" "$pkgdir/usr/share/licenses/{package_name}/LICENSE"
}}"""
    elif template == "lemonade-server":
        source_patch_cmds = "".join(
            f'  patch -Np1 -i "$srcdir/{patch_name}"\n'
            for patch_name in policy_pkg.get("source_patches", [])
        )
        build_body = f"""\
prepare() {{
  cd "$srcdir/{src_subdir}"

{source_patch_cmds.rstrip()}
}}

build() {{
  cd "$srcdir/{src_subdir}"

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  local amdclang="$CC"
  local amdclangxx="$CXX"
  local build_root="$srcdir/build-{package_name}"
  local install_root="/usr"

  cmake -B "${{build_root}}" -GNinja . \\
    -DCMAKE_C_COMPILER="${{amdclang}}" \\
    -DCMAKE_CXX_COMPILER="${{amdclangxx}}" \\
    -DCMAKE_BUILD_TYPE=Release \\
    -DCMAKE_INSTALL_PREFIX="${{install_root}}" \\
    -DCMAKE_C_FLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument" \\
    -DCMAKE_CXX_FLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument" \\
    -DBUILD_ELECTRON_APP=OFF \\
    -DBUILD_WEB_APP=ON

  cmake --build "${{build_root}}" -j"$(nproc)"
}}

package() {{
  cd "$srcdir/{src_subdir}"
  local build_root="$srcdir/build-{package_name}"

  DESTDIR="$pkgdir" cmake --install "${{build_root}}"

  rm -rf "$pkgdir/usr/share/applications" \\
         "$pkgdir/usr/share/pixmaps" \\
         "$pkgdir/usr/share/icons" \\
         "$pkgdir/usr/share/lemonade-app" \\
         "$pkgdir/usr/bin/lemonade-app"

  if [[ -d "$pkgdir/usr/share" ]]; then
    find "$pkgdir/usr/share" -type f \\( -name '*.desktop' -o -name '*.png' -o -name '*.svg' \\) -delete
  fi

  install -Dm644 /dev/stdin "$pkgdir/etc/lemonade/conf.d/10-llamacpp-gfx1151.conf" <<'EOF'
{chr(10).join(lemonade_llamacpp_env_lines())}
EOF

  install -Dm644 "$srcdir/{src_subdir}/LICENSE" "$pkgdir/usr/share/licenses/{package_name}/LICENSE"
}}"""
    elif template == "lemonade-app":
        build_body = f"""\
build() {{
  cd "$srcdir/{src_subdir}"

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  local amdclang="$CC"
  local amdclangxx="$CXX"
  local build_root="$srcdir/build-{package_name}"
  local install_root="/usr"

  cmake -B "${{build_root}}" -GNinja . \
    -DCMAKE_C_COMPILER="${{amdclang}}" \
    -DCMAKE_CXX_COMPILER="${{amdclangxx}}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${{install_root}}" \
    -DCMAKE_C_FLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument" \
    -DCMAKE_CXX_FLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument" \
    -DBUILD_ELECTRON_APP=OFF \
    -DBUILD_WEB_APP=OFF

  cmake --build "${{build_root}}" --target electron-app -j"$(nproc)"
}}

package() {{
  cd "$srcdir/{src_subdir}"
  local build_root="$srcdir/build-{package_name}"
  local _electron_root="$pkgdir/usr/share/lemonade-app"
  local _electron_output="${{build_root}}/app/linux-unpacked"

  install -dm755 "${{_electron_root}}"
  if [[ -d "${{_electron_output}}" ]]; then
    cp -a "${{_electron_output}}/." "${{_electron_root}}/"
  else
    echo "LEMONADE_APP_OUTPUT_MISSING: expected Electron artifacts under ${{_electron_output}}" >&2
    echo "HINT: lemonade electron-app currently writes to CMAKE_BINARY_DIR/app/linux-unpacked on Linux; adjust the renderer if upstream changes this." >&2
    return 1
  fi

  if [[ -f data/lemonade-app.desktop ]]; then
    install -Dm644 data/lemonade-app.desktop "$pkgdir/usr/share/applications/lemonade-app.desktop"
  elif [[ -f data/lemonade-web-app.desktop ]]; then
    install -Dm644 data/lemonade-web-app.desktop "$pkgdir/usr/share/applications/lemonade-app.desktop"
  fi

  if [[ -f src/app/assets/logo.svg ]]; then
    install -Dm644 src/app/assets/logo.svg "$pkgdir/usr/share/pixmaps/lemonade-app.svg"
  fi

  install -Dm644 "$srcdir/{src_subdir}/LICENSE" "$pkgdir/usr/share/licenses/{package_name}/LICENSE"
}}"""
    elif template == "scons-aocl-libm":
        prepare_lines.append(render_patch_prepare(recipe_pkg))
        post_package_lines.append(
            textwrap.dedent(
                """\
                if [[ -f "$pkgdir/usr/lib/libalm.so" ]]; then
                  patchelf --set-rpath /usr/lib "$pkgdir/usr/lib/libalm.so"
                fi"""
            ).rstrip()
        )
        build_body = f"""\
build() {{
  cd "$srcdir/{src_subdir}"

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  local amdclang="$CC"
  local amdclangxx="$CXX"

  if [[ ! -d .scons-venv ]]; then
    python -m venv .scons-venv
  fi

  source .scons-venv/bin/activate
  python -m pip install --upgrade pip
  python -m pip install scons

  scons -j"$(nproc)" \\
    ALM_CC="${{amdclang}}" \\
    ALM_CXX="${{amdclangxx}}" \\
    --arch_config=avx512 \\
    --aocl_utils_install_path=/usr \\
    --aocl_utils_link=0

  deactivate
}}

package() {{
  cd "$srcdir/{src_subdir}"

  install -dm755 "$pkgdir/usr/lib" "$pkgdir/usr/include"
  find build/aocl-release/src -name 'libalm*' -exec install -m755 {{}} "$pkgdir/usr/lib/" \\;

  if [[ -f build/aocl-release/src/compat/glibc-compat.o ]]; then
    install -m644 build/aocl-release/src/compat/glibc-compat.o "$pkgdir/usr/lib/"
  fi

  if [[ -d include ]]; then
    cp -a include/. "$pkgdir/usr/include/"
  fi

{textwrap.indent(post_package_lines[0], "  ")}
}}"""
    elif template == "autoconf-python":
        pybasever = ".".join(policy_pkg["upstream_version"].split(".")[:2])
        build_body = f"""\
prepare() {{
  cd "$srcdir/{src_subdir}"

  rm -r Modules/expat
  rm -r Modules/_decimal/libmpdec
}}

build() {{
  cd "$srcdir/{src_subdir}"

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  local amdclang="$CC"
  local amdclangxx="$CXX"
  local _debug_prefix="/usr/src/debug/{package_name}"
  local _base_cflags="-march=native -O3 -pipe -fno-plt -fexceptions -Wp,-D_FORTIFY_SOURCE=3 -Wformat -Werror=format-security -fstack-clash-protection -fcf-protection -mpclmul -g -ffile-prefix-map=$srcdir=${{_debug_prefix}} -flto=auto -ffat-lto-objects -fno-semantic-interposition"

  unset CFLAGS CXXFLAGS LDFLAGS CMAKE_C_FLAGS_RELEASE CMAKE_CXX_FLAGS_RELEASE \\
    CMAKE_EXE_LINKER_FLAGS CMAKE_SHARED_LINKER_FLAGS

  ./configure \\
    --prefix="{install_prefix}" \\
    --enable-shared \\
    --with-computed-gotos \\
    --enable-optimizations \\
    --with-lto \\
    --enable-ipv6 \\
    --with-system-expat \\
    --with-dbmliborder=gdbm:ndbm \\
    --with-system-libmpdec \\
    --enable-loadable-sqlite-extensions \\
    --without-ensurepip \\
    --with-tzpath=/usr/share/zoneinfo \\
    CC="${{amdclang}}" \\
    CXX="${{amdclangxx}}" \\
    CFLAGS="${{_base_cflags}} -famd-opt -Wno-error=unused-command-line-argument" \\
    CXXFLAGS="${{_base_cflags}} -famd-opt -Wno-error=unused-command-line-argument" \\
    LDFLAGS="-Wl,-O1 -Wl,--sort-common -Wl,--as-needed -Wl,-z,relro -Wl,-z,now -Wl,-z,pack-relative-relocs -flto=auto -fuse-ld=lld"

  make EXTRA_CFLAGS="${{_base_cflags}} -famd-opt -Wno-error=unused-command-line-argument" -j"$(nproc)"
}}

package() {{
  cd "$srcdir/{src_subdir}"
  make DESTDIR="$pkgdir" install

  local _debug_prefix="/usr/src/debug/{package_name}"
  local _sanitized_src="${{_debug_prefix}}/{src_subdir}"
  local _sysconfig="$pkgdir/usr/lib/python{pybasever}/_sysconfigdata__linux_x86_64-linux-gnu.py"
  local _sysconfig_json="$pkgdir/usr/lib/python{pybasever}/_sysconfig_vars__linux_x86_64-linux-gnu.json"
  local _config_makefile="$pkgdir/usr/lib/python{pybasever}/config-{pybasever}-x86_64-linux-gnu/Makefile"
  local _python_config="$pkgdir/usr/bin/python{pybasever}-config"

  sed -i \
    -e "s|$srcdir/{src_subdir}|${{_sanitized_src}}|g" \
    -e "s|$srcdir|${{_debug_prefix}}|g" \
    -e "s|/tmp/pkg/src/{src_subdir}|${{_sanitized_src}}|g" \
    "${{_sysconfig}}" "${{_sysconfig_json}}" "${{_config_makefile}}" "${{_python_config}}"
  rm -f "$pkgdir/usr/lib/python{pybasever}/__pycache__/_sysconfigdata__linux_x86_64-linux-gnu."*.pyc

  ln -sf python3 "$pkgdir/usr/bin/python"
  ln -sf python3-config "$pkgdir/usr/bin/python-config"
  ln -sf idle3 "$pkgdir/usr/bin/idle"
  ln -sf pydoc3 "$pkgdir/usr/bin/pydoc"
  ln -sf python{pybasever}.1 "$pkgdir/usr/share/man/man1/python.1"

  install -dm755 "$pkgdir/usr/lib/python{pybasever}/Tools/i18n" "$pkgdir/usr/lib/python{pybasever}/Tools/scripts"
  install -m755 Tools/i18n/msgfmt.py Tools/i18n/pygettext.py "$pkgdir/usr/lib/python{pybasever}/Tools/i18n/"
  install -m755 Tools/scripts/README Tools/scripts/*.py "$pkgdir/usr/lib/python{pybasever}/Tools/scripts/"

  install -Dm644 /dev/stdin "$pkgdir/usr/lib/python{pybasever}/EXTERNALLY-MANAGED" <<'EOF'
[externally-managed]
Error=To install Python packages system-wide, use pacman or a dedicated virtual environment.
EOF
}}"""
    elif template == "python-project-vllm":
        upstream_version = policy_pkg["upstream_version"]
        source_patches = policy_pkg.get("source_patches", [])
        patch_helper = ""
        patch_prepare_cmds = ""
        patch_build_cmds = ""
        if source_patches:
            patch_helper = """\
_apply_patch_if_needed() {
  local _patch_name="$1"
  local _patch=""

  if [[ -f "${srcdir}/${_patch_name}" ]]; then
    _patch="${srcdir}/${_patch_name}"
  elif [[ -f "${startdir}/${_patch_name}" ]]; then
    _patch="${startdir}/${_patch_name}"
  else
    printf 'missing patch file: %s\\n' "${_patch_name}" >&2
    return 1
  fi

  if patch --dry-run -R -Np1 -i "${_patch}" >/dev/null 2>&1; then
    return 0
  fi

  patch -Np1 -i "${_patch}"
}

"""
            patch_prepare_cmds = "".join(
                f'  _apply_patch_if_needed "{patch_name}"\n' for patch_name in source_patches
            )
            patch_build_cmds = patch_prepare_cmds
        build_body = f"""\
{patch_helper}prepare() {{
  cd "$srcdir/{src_subdir}"

{patch_prepare_cmds.rstrip()}
}}

build() {{
  cd "$srcdir/{src_subdir}"

{patch_build_cmds.rstrip()}

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  export CFLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument -DGLOG_USE_GLOG_EXPORT"
  export CXXFLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument -DGLOG_USE_GLOG_EXPORT"
  export CPPFLAGS="${{CPPFLAGS:-}} -DGLOG_USE_GLOG_EXPORT"
  export ROCM_HOME="/opt/rocm"
  export HIP_PATH="/opt/rocm"
  export PYTORCH_ROCM_ARCH="gfx1151"
  export CMAKE_PREFIX_PATH="/opt/rocm"
  export VLLM_VERSION_OVERRIDE="{upstream_version}"
  export VLLM_ROCM_USE_AITER=1

  rm -rf .deps/triton_kernels-*

  local _rocm_compat="$srcdir/.torch-rocm-compat"
  rm -rf "${{_rocm_compat}}"
  mkdir -p "${{_rocm_compat}}"
  if [[ -f /opt/rocm/lib/librocsolver.so.1 ]] && [[ ! -e /opt/rocm/lib/librocsolver.so.0 ]]; then
    # Temporary build-only shim for host torch import. Final integration
    # should rebuild torchvision/vllm against the local PyTorch package
    # once its ROCm linkage is import-clean.
    ln -sf /opt/rocm/lib/librocsolver.so.1 "${{_rocm_compat}}/librocsolver.so.0"
  fi
  export LD_LIBRARY_PATH="${{_rocm_compat}}:/opt/rocm/lib:${{LD_LIBRARY_PATH:-}}"

  mkdir -p dist
  rm -f dist/*.whl

  if ! pip wheel . --no-build-isolation --no-deps --wheel-dir dist -v; then
    unset VLLM_ROCM_USE_AITER
    python setup.py clean 2>/dev/null || true
    find . -name "*.so" -path "*/build/*" -delete 2>/dev/null || true
    pip wheel . --no-build-isolation --no-deps --wheel-dir dist -v
  fi
}}

package() {{
  cd "$srcdir/{src_subdir}"
  python -m installer --destdir="$pkgdir" dist/*.whl
}}"""
    elif template == "python-project-pytorch-rocm":
        upstream_version = policy_pkg["upstream_version"]
        prepare_lines.extend(
            [
                "# PyTorch's ROCm fork relies on vendored submodules and local hipify-generated sources.",
                'git -C "$srcdir/{src_subdir}" submodule sync --recursive'.format(src_subdir=src_subdir),
                'git -C "$srcdir/{src_subdir}" submodule update --init --recursive --force'.format(src_subdir=src_subdir),
                "# Match the recipe's ABI/runtime fixes on top of the Arch split-package baseline.",
                "sed -i 's|#include <numpy/arrayobject.h>|// Target numpy 2.0 C-API (0x12) for ABI compatibility with numpy >= 2.0.\\n#ifndef NPY_TARGET_VERSION\\n#define NPY_TARGET_VERSION 0x00000012\\n#endif\\n\\n#include <numpy/arrayobject.h>|' torch/csrc/utils/numpy_stub.h",
                "sed -i 's/list(APPEND HIP_HIPCC_FLAGS -fclang-abi-compat=17)/# Removed: causes ABI mismatch with host amdclang 22/' cmake/Dependencies.cmake",
                "sed -i 's/\"gfx90a\", \"gfx942\", \"gfx950\"/\"gfx90a\", \"gfx942\", \"gfx950\", \"gfx1151\"/' aten/src/ATen/Context.cpp",
                'python -c \'from pathlib import Path; paths=["aten/src/ATen/native/hip/linalg/BatchLinearAlgebra.cpp","aten/src/ATen/native/cuda/linalg/BatchLinearAlgebra.cpp"]; old="""#define AT_MAGMA_VERSION MAGMA_VERSION_MAJOR*100 + MAGMA_VERSION_MINOR*10 + MAGMA_VERSION_MICRO\\n\\n// Check that MAGMA never releases MAGMA_VERSION_MINOR >= 10 or MAGMA_VERSION_MICRO >= 10\\n#if MAGMA_VERSION_MINOR >= 10 || MAGMA_VERSION_MICRO >= 10\\n#error \\"MAGMA release minor or micro version >= 10, please correct AT_MAGMA_VERSION\\"\\n#endif\\n"""; new="""#define AT_MAGMA_VERSION_ENCODE(major, minor, micro) ((major) * 10000 + (minor) * 100 + (micro))\\n#define AT_MAGMA_VERSION AT_MAGMA_VERSION_ENCODE(MAGMA_VERSION_MAJOR, MAGMA_VERSION_MINOR, MAGMA_VERSION_MICRO)\\n#define AT_MAGMA_2_5_4 AT_MAGMA_VERSION_ENCODE(2, 5, 4)\\n"""; [p.write_text(p.read_text().replace(old, new).replace("AT_MAGMA_VERSION >= 254", "AT_MAGMA_VERSION >= AT_MAGMA_2_5_4")) for p in map(Path, paths)]\'',
            ]
        )
        build_body = f"""\
build() {{
  cd "$srcdir/{src_subdir}"

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  export CFLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument"
  export CXXFLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument"
  export LDFLAGS="-fuse-ld=lld"
  export PYTORCH_ROCM_ARCH="gfx1151"
  export USE_ROCM=1
  export USE_ROCM_CK_GEMM=1
  export USE_CUDA=0
  export USE_NCCL=0
  export USE_SYSTEM_NCCL=0
  export USE_RCCL=1
  export BUILD_TEST=0
  export USE_BENCHMARK=0
  export HIP_PATH="/opt/rocm"
  export ROCM_HOME="/opt/rocm"
  export CMAKE_PREFIX_PATH="/opt/rocm"
  export MAX_JOBS="$(nproc)"
  export PYTORCH_BUILD_VERSION="{upstream_version}"
  export PYTORCH_BUILD_NUMBER=1

  if [[ -f tools/amd_build/build_amd.py ]]; then
    python tools/amd_build/build_amd.py
  fi

  if [[ -f aten/src/ATen/hip/HIPGraph.hip ]] && grep -q 'cudaGraphConditionalHandle' aten/src/ATen/hip/HIPGraph.hip; then
    cat > aten/src/ATen/hip/HIPGraph.hip <<'EOF'
// !!! This is a file automatically generated by hipify!!!
#include "hip/hip_runtime.h"
#include <ATen/hip/HIPGraph.h>
#include <ATen/hip/Exceptions.h>

namespace at::cuda {{

// cudaGraphConditionalHandle / set_conditional_handle removed:
// CUDA 12.4+ feature with no HIP equivalent. The class declaration
// in HIPGraph.h does not include this method on ROCm builds.

}} // namespace at::cuda
EOF
  fi

  mkdir -p dist
  pip wheel . --no-build-isolation --no-deps --wheel-dir dist -v
}}

package() {{
  cd "$srcdir/{src_subdir}"
  local _wheel
  _wheel="$(ls dist/torch-*.whl 2>/dev/null | tail -n 1)"
  python -m installer --destdir="$pkgdir" "$_wheel"

  local _site="$pkgdir/usr/lib/python3.14/site-packages"
  if [[ -d "${{_site}}/torch/lib" ]]; then
    local _so _runpath
    for _so in "${{_site}}"/torch/lib/lib*.so; do
      [[ -f "${{_so}}" ]] || continue
      _runpath="$(readelf -d "${{_so}}" 2>/dev/null | grep 'RUNPATH' || true)"
      if grep -q 'pytorch/build' <<<"${{_runpath}}"; then
        patchelf --set-rpath "/opt/rocm/lib:\\$ORIGIN" "${{_so}}" 2>/dev/null || true
      elif readelf -d "${{_so}}" 2>/dev/null | grep -Eq 'libamdhip64|librocm_smi'; then
        patchelf --add-rpath "/opt/rocm/lib" "${{_so}}" 2>/dev/null || true
      fi
    done

    for _so in "${{_site}}"/torch/_C*.so; do
      [[ -f "${{_so}}" ]] || continue
      if readelf -d "${{_so}}" 2>/dev/null | grep -q 'pytorch/build'; then
        patchelf --set-rpath "/opt/rocm/lib:\\$ORIGIN/lib" "${{_so}}" 2>/dev/null || true
      fi
    done

    if [[ -f "${{_site}}/torch/lib/libtorch_hip.so" ]] && ! readelf -d "${{_site}}/torch/lib/libtorch_hip.so" 2>/dev/null | grep -q 'librocm_smi64'; then
      patchelf --add-needed librocm_smi64.so "${{_site}}/torch/lib/libtorch_hip.so" 2>/dev/null || true
    fi
  fi
}}"""
    elif template == "python-project-torchvision-rocm":
        build_body = f"""\
build() {{
  cd "$srcdir/{src_subdir}"

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  export CFLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument -DGLOG_USE_GLOG_EXPORT"
  export CXXFLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument -DGLOG_USE_GLOG_EXPORT"
  export CPPFLAGS="${{CPPFLAGS:-}} -DGLOG_USE_GLOG_EXPORT"
  export ROCM_HOME="/opt/rocm"
  export ROCM_PATH="/opt/rocm"
  export HIP_ROOT_DIR="/opt/rocm"
  export PYTORCH_ROCM_ARCH="gfx1151"
  export TORCH_CUDA_ARCH_LIST=""
  export FORCE_CUDA=0
  export FORCE_MPS=0
  python - <<'PY'
from pathlib import Path
path = Path("setup.py")
text = path.read_text()
old = '            nvcc_flags = []'
new = '            nvcc_flags = ["-DGLOG_USE_GLOG_EXPORT"]'
if old in text:
    text = text.replace(old, new, 1)
path.write_text(text)
PY
  local _compat_libdir="$srcdir/.torch-rocm-compat"
  mkdir -p "${{_compat_libdir}}"
  ln -sf /opt/rocm/lib/librocsolver.so.1 "${{_compat_libdir}}/librocsolver.so.0"
  export LD_LIBRARY_PATH="${{_compat_libdir}}:/opt/rocm/lib:${{LD_LIBRARY_PATH:-}}"

  mkdir -p dist
  pip wheel . --no-build-isolation --no-deps --wheel-dir dist -v
}}

package() {{
  cd "$srcdir/{src_subdir}"
  local _wheel
  _wheel="$(ls dist/torchvision-*.whl 2>/dev/null | tail -n 1)"
  python -m installer --destdir="$pkgdir" "$_wheel"
}}"""
    elif template == "python-project-triton-rocm":
        python_subdir = f"{src_subdir}/python"
        prepare_lines.extend(
            [
                "# Keep Arch's Python-3.14 and setuptools compatibility deltas on top of the ROCm performance fork.",
                "sed -i '/requires = \\[/s/.*/requires = [\"setuptools\", \"wheel\", \"pybind11>=2.13.1\"]/' python/pyproject.toml",
                "sed -i 's/-Werror//' CMakeLists.txt",
                "git cherry-pick -n c44b870bdd9e1ea8933fd4057b6b59a5e6e5407b || true",
            ]
        )
        build_body = f"""\
build() {{
  cd "$srcdir/{python_subdir}"
  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  export ROCM_HOME="/opt/rocm"
  export ROCM_PATH="/opt/rocm"
  unset LLVM_SYSPATH
  export TRITON_BUILD_PROTON=OFF
  if command -v ccache >/dev/null 2>&1; then
    export TRITON_BUILD_WITH_CCACHE=true
  else
    unset TRITON_BUILD_WITH_CCACHE
  fi

  python -m build --wheel --no-isolation
}}

package() {{
  cd "$srcdir/{python_subdir}"
  python -m installer --destdir="$pkgdir" dist/*.whl
  install -Dm644 "$srcdir/{src_subdir}/LICENSE" "$pkgdir/usr/share/licenses/{package_name}/LICENSE"
}}"""
    elif template == "python-project-aotriton":
        prepare_lines.extend(
            [
                "# Arch-style source prep: AOTriton expects its bundled submodules to be initialized before configure.",
                'git -C "$srcdir/{src_subdir}" submodule sync --recursive'.format(src_subdir=src_subdir),
                'git -C "$srcdir/{src_subdir}" submodule update --init --recursive --force'.format(src_subdir=src_subdir),
                "# Keep vendored Triton aligned with the standalone Python-3.14 compatibility fix we already apply in python-triton-gfx1151.",
                'git -C "$srcdir/{src_subdir}/third_party/triton" cherry-pick -n c44b870bdd9e1ea8933fd4057b6b59a5e6e5407b || true'.format(src_subdir=src_subdir),
            ]
        )
        build_body = f"""\
build() {{
  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  if [[ -n "${{AOTRITON_REUSE_BUILD:-}}" && -f "$srcdir/build/build.ninja" ]]; then
    :
  else
    if [[ -d "$srcdir/build" ]]; then
      chmod -R u+w "$srcdir/build" 2>/dev/null || true
    fi
    rm -rf "$srcdir/build"
  fi
  local cmake_args=(
    -G Ninja
    -Wno-dev
    -S "$srcdir/{src_subdir}"
    -B "$srcdir/build"
    -D CMAKE_C_COMPILER="$CC"
    -D CMAKE_CXX_COMPILER="$CXX"
    -D CMAKE_CXX_FLAGS="$CXXFLAGS -DNDEBUG"
    -D CMAKE_BUILD_TYPE=None
    -D CMAKE_INSTALL_PREFIX=/usr
    -D AOTRITON_GPU_BUILD_TIMEOUT=0
    -D AOTRITON_USE_TORCH=OFF
    -D AOTRITON_TARGET_ARCH="gfx1151"
  )
  export TRITON_APPEND_CMAKE_ARGS="-DTRITON_BUILD_UT=OFF"
  if [[ -n "${{AOTRITON_REUSE_BUILD:-}}" && -f "$srcdir/build/build.ninja" ]]; then
    cmake --build "$srcdir/build"
  else
    cmake "${{cmake_args[@]}}"
    cmake --build "$srcdir/build"
  fi
}}

package() {{
  DESTDIR="$pkgdir" cmake --install "$srcdir/build"
}}"""
    elif template == "python-project-aiter":
        source_patch_cmds = "".join(
            f'  patch -Np1 -i "$srcdir/{patch_name}"\n'
            for patch_name in policy_pkg.get("source_patches", [])
        )
        build_body = f"""\
prepare() {{
  cd "$srcdir/{src_subdir}"

{source_patch_cmds.rstrip()}
}}

build() {{
  cd "$srcdir/{src_subdir}"

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  export PREBUILD_KERNELS=0
  export AITER_GPU_ARCH=gfx1151
  export CFLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument"
  export CXXFLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument"
  local _ck_submodule="$srcdir/{src_subdir}/3rdparty/composable_kernel"
  if [[ ! -d "${{_ck_submodule}}/include" ]]; then
    git submodule sync 3rdparty/composable_kernel
    git submodule update --init 3rdparty/composable_kernel
  fi
  [[ -d "${{_ck_submodule}}/example/ck_tile/01_fmha" ]] || {{
    echo "CK submodule missing fmha codegen at ${{_ck_submodule}}" >&2
    return 1
  }}
  export CK_DIR="${{_ck_submodule}}"

  mkdir -p dist
  pip wheel . --no-build-isolation --no-deps --wheel-dir dist -v
}}

package() {{
  cd "$srcdir/{src_subdir}"
  python -m installer --destdir="$pkgdir" dist/*.whl
}}"""
    elif template == "rust-wheel-pypi":
        build_body = f"""\
build() {{
  cd "$srcdir/{src_subdir}"

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  local _debug_prefix="/usr/src/debug/{package_name}"
  export CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER="$CC"
  export RUSTFLAGS="-C target-cpu=znver5 -C opt-level=3 --remap-path-prefix=$srcdir=${{_debug_prefix}}"
  unset CFLAGS CXXFLAGS LDFLAGS

  python -m build --wheel --no-isolation
}}

package() {{
  cd "$srcdir/{src_subdir}"
  python -m installer --destdir="$pkgdir" dist/*.whl

  local _debug_prefix="/usr/src/debug/{package_name}"
  find "$pkgdir/usr/lib" -type f \\( -name '*.so' -o -path '*/sboms/*.json' \\) -print0 | while IFS= read -r -d '' _file; do
    sed -i \
      -e "s|$srcdir/{src_subdir}|${{_debug_prefix}}/{src_subdir}|g" \
      -e "s|$srcdir|${{_debug_prefix}}|g" \
      -e "s|/tmp/pkg/src/{src_subdir}|${{_debug_prefix}}/{src_subdir}|g" \
      "$_file" 2>/dev/null || true
  done
}}"""
    elif template == "native-wheel-pypi":
        build_body = f"""\
build() {{
  cd "$srcdir/{src_subdir}"

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  local _base_flags="-O3 -march=native -mprefer-vector-width=512 -mavx512f -mavx512dq -mavx512vl -mavx512bw -mllvm -enable-gvn-hoist -mllvm -enable-gvn-sink -famd-opt -Wno-error=unused-command-line-argument"
  local _wheel_flags
  _wheel_flags="$(printf '%s' "${{_base_flags}}" | sed -E 's/-mllvm (-[^ ]+)/-Xclang -mllvm -Xclang \\1/g; s/-famd-opt//g; s/  +/ /g; s/^ +| +$//g')"

  export CFLAGS="${{_wheel_flags}}"
  export CXXFLAGS="${{_wheel_flags}}"
  export LDFLAGS="-famd-opt"

  python -m build --wheel --no-isolation
}}

package() {{
  cd "$srcdir/{src_subdir}"
  python -m installer --destdir="$pkgdir" dist/*.whl
}}"""
    elif template == "meta-package":
        build_body = f"""\
build() {{
  :
}}

package() {{
  install -d "$pkgdir/usr/share/doc/{package_name}"
  printf '%s\\n' 'Meta package for {package_name}.' > "$pkgdir/usr/share/doc/{package_name}/README"
}}"""
    else:
        print(f"UNSUPPORTED_RECIPE_METHOD: {template}", file=sys.stderr)
        print("HINT: add a template handler to render_recipe_scaffolds.py for this recipe package type.", file=sys.stderr)
        raise SystemExit(2)

    prepare_body = ""
    if prepare_lines:
        prepare_body = "prepare() {\n  cd \"$srcdir/%s\"\n\n%s\n}\n\n" % (
            src_subdir,
            textwrap.indent("\n".join(line for line in prepare_lines if line), "  ").lstrip(),
        )
    return prepare_body, build_body, "\n".join(post_package_lines)


def render_pkgbuild(package_name: str, policy_pkg: dict, recipe_pkg: dict, version: str, defaults: dict) -> str:
    provides = policy_pkg.get("provides", [])
    conflicts = policy_pkg.get("conflicts", [])
    replaces = policy_pkg.get("replaces", [])
    depends = policy_pkg.get("depends", [])
    makedepends = policy_pkg.get("makedepends", [])
    optdepends = policy_pkg.get("optdepends", [])
    options = policy_pkg.get("options", [])
    license_items = policy_pkg.get("license", [])
    prepare_body, method_body, _ = render_method_body(package_name, policy_pkg, recipe_pkg)
    source_refs, sha256sums = render_source_refs(policy_pkg, recipe_pkg)

    pkgrel = preserved_pkgrel(package_name, version)
    header = textwrap.dedent(
        f"""\
        # Maintainer: nisavid
        # Generated by tools/render_recipe_scaffolds.py
        # Recipe source: {defaults['recipe_repo']} ({defaults['recipe_subdir']})
        # Recipe attribution: {defaults['recipe_author']}
        # Package recipe key: {policy_pkg['recipe_key']}
        """
    ).rstrip()

    pkgbuild = f"""{header}

pkgname={package_name}
pkgver={version}
pkgrel={pkgrel}
pkgdesc={shell_quote(policy_pkg['pkgdesc'])}
arch=('x86_64')
url={shell_quote(policy_pkg['url'])}
license={bash_array(license_items)}
depends={bash_array(depends)}
makedepends={bash_array(makedepends)}
optdepends={bash_array(optdepends)}
options={bash_array(options)}
provides={bash_array(provides)}
conflicts={bash_array(conflicts)}
replaces={bash_array(replaces)}
source={source_refs}
sha256sums={sha256sums}

{prepare_body}{method_body}
"""
    return pkgbuild.rstrip() + "\n"


def package_role(package_name: str, policy_pkg: dict) -> str | None:
    template = policy_pkg.get("template")
    if template == "lemonade-server":
        return "server-runtime"
    if template == "lemonade-app":
        return "desktop-app"
    if template == "meta-package":
        return "meta-package"
    if template == "llama-cpp":
        return "backend-runtime"
    return None


def optional_backends(package_name: str, policy_pkg: dict) -> list[str]:
    template = policy_pkg.get("template")
    if template == "lemonade-server":
        return ["llama.cpp-hip-gfx1151", "llama.cpp-vulkan-gfx1151"]
    if template == "meta-package" and package_name == "lemonade":
        return ["llama.cpp-hip-gfx1151", "llama.cpp-vulkan-gfx1151"]
    return []


def render_recipe_json(package_name: str, policy_pkg: dict, recipe_pkg: dict, version: str, defaults: dict) -> str:
    authoritative_reference = policy_pkg.get("authoritative_reference")
    if authoritative_reference is None:
        references = policy_pkg.get("arch_reference", [])
        authoritative_reference = "" if policy_pkg.get("baseline_kind") == "meta-aggregate" else (references[0] if references else "")
    advisory_references = policy_pkg.get("advisory_references")
    if advisory_references is None:
        references = policy_pkg.get("arch_reference", [])
        advisory_references = references[1:] if len(references) > 1 else []
    recipe_notes = policy_pkg.get("recipe_notes_override", recipe_pkg.get("notes", "").strip())
    payload = {
        "name": package_name,
        "package_name": package_name,
        "pkgver": version,
        "policy": policy_pkg,
        "recipe": {
            "repo": recipe_pkg.get("repo"),
            "branch": recipe_pkg.get("branch"),
            "src_dir": recipe_pkg.get("src_dir"),
            "method": recipe_pkg.get("method"),
            "phase": recipe_pkg.get("phase"),
            "steps": recipe_pkg.get("steps", []),
            "depends_on": recipe_pkg.get("depends_on", []),
            "notes": recipe_notes,
            "patches": recipe_pkg.get("patches", []),
        },
        "provenance": defaults,
    }
    payload["maintenance"] = {
        "authoritative_reference": authoritative_reference,
        "advisory_references": advisory_references,
        "divergence_notes": policy_pkg.get("divergence_notes", []),
        "update_notes": policy_pkg.get("update_notes", []),
        "source_patches": policy_pkg.get("source_patches", []),
    }
    role = package_role(package_name, policy_pkg)
    if role:
        payload["role"] = role
    backends = optional_backends(package_name, policy_pkg)
    if backends:
        payload["optional_backends"] = backends
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def render_readme(package_name: str, policy_pkg: dict, recipe_pkg: dict, version: str) -> str:
    notes = policy_pkg.get("scaffold_notes", [])
    recipe_notes = policy_pkg.get("recipe_notes_override", recipe_pkg.get("notes", "").strip())
    patch_count = len(recipe_pkg.get("patches", [])) + len(policy_pkg.get("source_patches", []))
    steps = ", ".join(str(step) for step in recipe_pkg.get("steps", []))
    depends_on = ", ".join(recipe_pkg.get("depends_on", [])) or "none"
    references = ", ".join(policy_pkg.get("arch_reference", [])) or "none"
    authoritative_reference = policy_pkg.get("authoritative_reference")
    if authoritative_reference is None:
        reference_list = policy_pkg.get("arch_reference", [])
        authoritative_reference = "none" if policy_pkg.get("baseline_kind") == "meta-aggregate" else (reference_list[0] if reference_list else "none")
    advisory_references = policy_pkg.get("advisory_references")
    if advisory_references is None:
        reference_list = policy_pkg.get("arch_reference", [])
        advisory_references = reference_list[1:] if len(reference_list) > 1 else []
    role = package_role(package_name, policy_pkg)
    backends = optional_backends(package_name, policy_pkg)

    lines = [f"# {package_name}", "", "## Maintenance Snapshot", ""]
    if role:
        lines.append(f"- Role: `{role}`")
    if backends:
        lines.append("- Optional backends:")
        for backend in backends:
            lines.append(f"  - `{backend}`")
    lines.extend(
        [
        f"- Recipe package key: `{policy_pkg['recipe_key']}`",
        f"- Scaffold template: `{policy_pkg['template']}`",
        f"- Recipe build method: `{recipe_pkg.get('method', 'unknown')}`",
        f"- Upstream repo: `{recipe_pkg.get('repo', '')}`",
        f"- Derived pkgver seed: `{version}`",
        f"- Recipe steps: `{steps}`",
        f"- Recipe dependencies: `{depends_on}`",
        f"- Recorded reference packages: `{references}`",
        f"- Authoritative reference package: `{authoritative_reference}`",
        f"- Advisory reference packages: `{', '.join(advisory_references) or 'none'}`",
        f"- Applied source patch files/actions: `{patch_count}`",
        "",
        "## Recipe notes",
        "",
        recipe_notes or "No inline recipe notes recorded.",
        "",
        "## Scaffold notes",
        "",
    ]
    )
    for note in notes:
        lines.append(f"- {note}")
    divergence_notes = policy_pkg.get("divergence_notes", [])
    if divergence_notes:
        lines.extend(["", "## Intentional Divergences", ""])
        for note in divergence_notes:
            lines.append(f"- {note}")
    update_notes = policy_pkg.get("update_notes", [])
    if update_notes:
        lines.extend(["", "## Update Notes", ""])
        for note in update_notes:
            lines.append(f"- {note}")
    lines.extend(
        [
            "",
            "## Maintainer Starting Points",
            "",
            "- Diff the package against its recorded authoritative reference first.",
            "- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.",
            "- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.",
            "- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.",
            "",
        ]
    )
    if policy_pkg.get("source_type") in {"tarball"} or policy_pkg.get("template", "").startswith("python-project-"):
        lines[-1:-1] = [
            "- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.",
        ]
    return "\n".join(lines)


def ensure_recipe_package(recipe_manifest: dict, recipe_key: str) -> dict:
    recipe_packages = recipe_manifest.get("packages", {})
    recipe_pkg = recipe_packages.get(recipe_key)
    if recipe_pkg is None:
        print(f"MISSING_RECIPE_PACKAGE: {recipe_key}", file=sys.stderr)
        print("HINT: the policy file references a recipe package key that is not present in vllm-packages.yaml.", file=sys.stderr)
        raise SystemExit(2)
    return recipe_pkg


def main() -> int:
    args = parse_args()
    packaging_root = Path(__file__).resolve().parents[1]
    policy_path = packaging_root / args.policy
    output_root = packaging_root / args.output_root
    recipe_root = Path(args.recipe_root).resolve()
    recipe_dir = recipe_root / args.recipe_subdir

    policy = load_toml(policy_path)
    defaults = dict(policy.get("defaults", {}))
    recipe_manifest = load_recipe_manifest(recipe_dir)
    selected = set(args.only)
    available = set(policy.get("packages", {}).keys())
    unknown = sorted(selected - available)
    if unknown:
        print(f"UNKNOWN_PACKAGE_SELECTION: {', '.join(unknown)}", file=sys.stderr)
        print("HINT: use one of the package names defined in policies/recipe-packages.toml.", file=sys.stderr)
        return 2

    for package_name, policy_pkg in policy.get("packages", {}).items():
        if selected and package_name not in selected:
            continue
        recipe_pkg = ensure_recipe_package(recipe_manifest, policy_pkg["recipe_key"])
        version = compute_version(recipe_root, args.recipe_subdir, policy_pkg["upstream_version"])
        package_dir = output_root / package_name
        package_dir.mkdir(parents=True, exist_ok=True)

        (package_dir / "PKGBUILD").write_text(
            render_pkgbuild(package_name, policy_pkg, recipe_pkg, version, defaults),
            encoding="utf-8",
        )
        (package_dir / "recipe.json").write_text(
            render_recipe_json(package_name, policy_pkg, recipe_pkg, version, defaults),
            encoding="utf-8",
        )
        (package_dir / "README.md").write_text(
            render_readme(package_name, policy_pkg, recipe_pkg, version),
            encoding="utf-8",
        )
        print(f"rendered {package_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
