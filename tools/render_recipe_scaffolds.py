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

from recipe_repo import RECIPE_ROOT_ENV_VAR, resolve_recipe_dir, resolve_recipe_root

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
    parser.add_argument(
        "--recipe-root",
        help=(
            "git repo root containing the recipe; defaults to the repo-local "
            "upstream/ai-notes submodule or the "
            f"{RECIPE_ROOT_ENV_VAR} environment variable"
        ),
    )
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


def git_output(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def recipe_revision(repo: Path, subdir: str) -> dict[str, int | str]:
    commit_count = git_output(repo, "rev-list", "--count", "HEAD", "--", subdir)
    latest = git_output(repo, "log", "-1", "--date=format:%Y%m%d", "--format=%cd %h", "--", subdir)
    if not latest:
        raise RuntimeError(f"no git history found for path '{subdir}' in {repo}")
    commit_date, short_sha = latest.split()
    return {
        "recipe_commit": short_sha,
        "recipe_date": commit_date,
        "recipe_history_count": int(commit_count),
    }


def compiler_env_snippet(compiler_root: str) -> str:
    return textwrap.dedent(
        """\
_setup_compiler_env() {
  local _compiler_root="__COMPILER_ROOT__"
  local _ccache_dir="$srcdir/.ccache/bin"
  local _ccache_cache="$srcdir/.ccache/cache"
  if command -v ccache >/dev/null 2>&1; then
    mkdir -p "${_ccache_dir}" "${_ccache_cache}"
    local _ccache_bin _name
    _ccache_bin="$(command -v ccache)"
    for _name in clang clang++ clang-22 amdclang amdclang++ hipcc hipcc.pl gcc g++ cc c++; do
      ln -sf "${_ccache_bin}" "${_ccache_dir}/${_name}"
    done
    export PATH="${_ccache_dir}:$PATH"
    export CCACHE_BASEDIR="$srcdir"
    export CCACHE_DIR="${_ccache_cache}"
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
    extra_sources = policy_pkg.get("extra_sources")
    if not extra_sources:
        extra_sources = list(policy_pkg.get("source_patches", []))
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
    needs_archive_checksum = source_type == "tarball" or template in {"rust-wheel-pypi", "native-wheel-pypi"}
    sha256sums = policy_pkg.get("sha256sums", [] if needs_archive_checksum else ["SKIP"])
    if len(sha256sums) != 1:
        print("SOURCE_REF_MISMATCH: implicit source refs need exactly one sha256sum", file=sys.stderr)
        print("HINT: add one checksum for the generated source URL in policies/recipe-packages.toml.", file=sys.stderr)
        raise SystemExit(2)
    if needs_archive_checksum:
        if sha256sums[0] == "SKIP":
            print("SOURCE_REF_MISMATCH: implicit archive source refs need a concrete sha256sum", file=sys.stderr)
            print("HINT: add one checksum for the generated source URL in policies/recipe-packages.toml.", file=sys.stderr)
            raise SystemExit(2)
    return bash_array([source_ref] + extra_sources), bash_array(sha256sums + extra_sha256sums)


def slugify_step(step: int) -> str:
    return f"step-{step}"


def render_patch_prepare(recipe_pkg: dict, file_rewrites: dict[str, str] | None = None) -> str:
    lines: list[str] = []
    file_rewrites = file_rewrites or {}
    for patch in recipe_pkg.get("patches", []):
        patch_type = patch.get("type")
        if patch_type != "sed":
            if patch_type == "patchelf_rpath":
                continue
            print(f"UNSUPPORTED_PATCH_TYPE: {patch_type}", file=sys.stderr)
            print("HINT: extend render_recipe_scaffolds.py to translate this patch type into PKGBUILD logic.", file=sys.stderr)
            raise SystemExit(2)
        file_name = file_rewrites.get(patch["file"], patch["file"])
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
        f"LEMONADE_LLAMACPP_ROCM_VERSION={hip_rev}",
        f"LEMONADE_LLAMACPP_VULKAN_VERSION={vulkan_rev}",
        f"LEMONADE_LLAMACPP_ROCM_RELEASE_URL=https://github.com/ggml-org/llama.cpp/releases/tag/{hip_rev}",
        f"LEMONADE_LLAMACPP_VULKAN_RELEASE_URL=https://github.com/ggml-org/llama.cpp/releases/tag/{vulkan_rev}",
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
  rm -f "$pkgdir${{install_root}}/bin"/test-*
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
    elif template == "stable-diffusion-cpp":
        prepare_lines.extend(
            [
                "rm -rf ggml examples/server/frontend thirdparty/libwebm thirdparty/libwebp",
                "mkdir -p examples/server thirdparty",
                'cp -a "$srcdir/ggml" ggml',
                'cp -a "$srcdir/sdcpp-webui" examples/server/frontend',
                'cp -a "$srcdir/libwebm" thirdparty/libwebm',
                'cp -a "$srcdir/libwebp" thirdparty/libwebp',
            ]
        )
        for patch_name in policy_pkg.get("source_patches", []):
            prepare_lines.extend(
                [
                    f'if ! patch --dry-run -R -Np1 -i "$srcdir/{patch_name}" >/dev/null 2>&1; then',
                    f'  patch -Np1 -i "$srcdir/{patch_name}"',
                    "fi",
                ]
            )
        install_root = f"/opt/{package_name}"
        build_body = f"""\
build() {{
  cd "$srcdir/{src_subdir}"

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  local amdclang="$CC"
  local amdclangxx="$CXX"
  local build_root="$srcdir/build-vulkan"
  local install_root="{install_root}"
  local _debug_prefix="/usr/src/debug/{package_name}"
  local _debug_map="-ffile-prefix-map=$srcdir=${{_debug_prefix}}"
  local _cpu_flags="-O3 -DNDEBUG -march=native -flto=thin -fno-semantic-interposition -mprefer-vector-width=512 -mavx512f -mavx512dq -mavx512vl -mavx512bw -famd-opt -Wno-error=unused-command-line-argument ${{_debug_map}}"
  local _aggressive_flags="-mllvm -polly -mllvm -polly-vectorizer=stripmine -mllvm -inline-threshold=600 -mllvm -unroll-threshold=150 -mllvm -adce-remove-loops"
  local _probe_src="$srcdir/.sdcpp-flag-probe.c"
  local _probe_obj="$srcdir/.sdcpp-flag-probe.o"
  printf '%s\\n' 'int main(void) {{ return 0; }}' > "${{_probe_src}}"
  if "${{amdclang}}" -O2 -x c -c "${{_probe_src}}" -o "${{_probe_obj}}" ${{_aggressive_flags}} >/dev/null 2>&1; then
    _cpu_flags="${{_cpu_flags}} ${{_aggressive_flags}}"
  fi
  rm -f "${{_probe_src}}" "${{_probe_obj}}"
  local _linker_flags="-flto=thin -fuse-ld=lld -L/usr/lib -lalm"

  rm -rf "${{build_root}}"
  cmake -B "${{build_root}}" -S . -GNinja \\
    -DCMAKE_BUILD_TYPE=Release \\
    -DCMAKE_C_COMPILER="${{amdclang}}" \\
    -DCMAKE_CXX_COMPILER="${{amdclangxx}}" \\
    -DCMAKE_C_FLAGS="${{_cpu_flags}}" \\
    -DCMAKE_CXX_FLAGS="${{_cpu_flags}}" \\
    -DCMAKE_EXE_LINKER_FLAGS="${{_linker_flags}}" \\
    -DCMAKE_SHARED_LINKER_FLAGS="${{_linker_flags}}" \\
    -DCMAKE_INSTALL_PREFIX="${{install_root}}" \\
    -DCMAKE_CXX_CLANG_TIDY=/bin/true \\
    -DSD_VULKAN=ON \\
    -DSD_BUILD_EXAMPLES=ON \\
    -DSD_BUILD_SHARED_LIBS=OFF \\
    -DSD_WEBP=ON \\
    -DSD_WEBM=ON \\
    -DGGML_NATIVE=ON \\
    -DGGML_LTO=ON \\
    -DGGML_OPENMP=ON \\
    -DGGML_CCACHE=ON \\
    -DGGML_VULKAN_CHECK_RESULTS=OFF \\
    -DGGML_VULKAN_VALIDATE=OFF \\
    -DGGML_VULKAN_DEBUG=OFF

  cmake --build "${{build_root}}"
}}

package() {{
  cd "$srcdir/{src_subdir}"
  local build_root="$srcdir/build-vulkan"
  local install_root="{install_root}"

  DESTDIR="$pkgdir" cmake --install "${{build_root}}"
  rm -rf "$pkgdir${{install_root}}/include" "$pkgdir${{install_root}}/lib"
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/{package_name}/LICENSE"
  install -d "$pkgdir/usr/bin" "$pkgdir${{install_root}}"
  printf '%s\\n' "{policy_pkg['upstream_version']}" > "$pkgdir${{install_root}}/version.txt"
  printf '%s\\n' "vulkan" > "$pkgdir${{install_root}}/backend.txt"
  cat > "$pkgdir${{install_root}}/build-info.env" <<EOF
PROJECT=stable-diffusion.cpp
BACKEND=vulkan
SOURCE_REVISION={policy_pkg.get('upstream_revision', policy_pkg['upstream_version'])}
PACKAGE={package_name}
EOF

  if command -v patchelf >/dev/null 2>&1; then
    local _bin
    for _bin in "$pkgdir${{install_root}}/bin"/sd-cli "$pkgdir${{install_root}}/bin"/sd-server; do
      [[ -f "${{_bin}}" ]] || continue
      patchelf --set-rpath "/usr/lib" "${{_bin}}" 2>/dev/null || true
    done
  fi

  _install_wrapper() {{
    local _tool="$1"
    local _wrapper="$2"
    [[ -x "$pkgdir${{install_root}}/bin/${{_tool}}" ]] || return 0
    cat > "$pkgdir/usr/bin/${{_wrapper}}" <<EOF
#!/usr/bin/env bash
exec {install_root}/bin/${{_tool}} "\\$@"
EOF
    chmod 755 "$pkgdir/usr/bin/${{_wrapper}}"
  }}
  _install_wrapper sd-cli sd-cli-vulkan-gfx1151
  _install_wrapper sd-server sd-server-vulkan-gfx1151
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

  export npm_config_cache="$srcdir/.npm-cache"
  export npm_config_update_notifier=false

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

  rm -rf "${{build_root}}"
  cmake -B "${{build_root}}" -GNinja . \
    -DCMAKE_C_COMPILER="${{amdclang}}" \
    -DCMAKE_CXX_COMPILER="${{amdclangxx}}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${{install_root}}" \
    -DCMAKE_C_FLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument" \
    -DCMAKE_CXX_FLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument" \
    -DBUILD_ELECTRON_APP=OFF \
    -DBUILD_WEB_APP=OFF

  cmake --build "${{build_root}}" --target tauri-app -j"$(nproc)"
}}

package() {{
  cd "$srcdir/{src_subdir}"
  local build_root="$srcdir/build-{package_name}"
  local _app_root="$pkgdir/usr/share/lemonade-app"
  local _tauri_output="${{build_root}}/app/lemonade-app"

  if [[ -f "${{_tauri_output}}" ]]; then
    install -Dm755 "${{_tauri_output}}" "${{_app_root}}/lemonade-app"
  else
    echo "LEMONADE_APP_OUTPUT_MISSING: expected Tauri binary at ${{_tauri_output}}" >&2
    echo "HINT: lemonade tauri-app currently writes to CMAKE_BINARY_DIR/app/lemonade-app on Linux; adjust the renderer if upstream changes this." >&2
    return 1
  fi

  install -Dm755 /dev/stdin "$pkgdir/usr/bin/lemonade-app" <<'EOF'
#!/bin/sh
exec /usr/share/lemonade-app/lemonade-app "$@"
EOF

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
        source_patches = policy_pkg.get("source_patches", [])
        if source_patches:
            prepare_lines.extend(
                f'patch -Np1 -i "$srcdir/{patch_name}"' for patch_name in source_patches
            )
        else:
            prepare_lines.append(
                render_patch_prepare(recipe_pkg, policy_pkg.get("recipe_patch_file_rewrites"))
            )
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
  local amdclang="$(command -v "$CC")"
  local amdclangxx="$(command -v "$CXX")"

  scons -j"$(nproc)" \\
    ALM_CC="${{amdclang}}" \\
    ALM_CXX="${{amdclangxx}}" \\
    --arch_config=avx512 \\
    --aocl_utils_install_path=/usr \\
    --aocl_utils_link=0
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
        vllm_srcdir = src_subdir
        if src_subdir == f"vllm-{upstream_version}":
            vllm_srcdir = "vllm-${pkgver}"
        vllm_source_prelude = f"""\
_vllm_srcdir="{vllm_srcdir}"
_vllm_tarball="v${{pkgver}}.tar.gz"

"""
        vllm_patch_vars = ""
        vllm_patch_apply_lines = "".join(
            f'  _apply_patch_if_needed "{patch_name}"\n'
            for patch_name in source_patches
        )
        if len(source_patches) == 1:
            vllm_patch_name = source_patches[0].replace(upstream_version, "${pkgver}")
            vllm_patch_vars = f'_vllm_source_patch="{vllm_patch_name}"\n'
            vllm_patch_apply_lines = '  _apply_patch_if_needed "${_vllm_source_patch}"\n'
        if source_patches:
            patch_helper = """\
__PATCH_VARS__

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

  patch -Np1 -i "${_patch}"
}

_reset_source_tree() {
  rm -rf "${srcdir}/${_vllm_srcdir}"
  bsdtar -xf "${srcdir}/${_vllm_tarball}" -C "${srcdir}"
}

_source_tree_has_all_source_patches() {
  [[ -f pyproject.toml ]] || return 1
  grep -Fq 'requires-python = ">=3.10,<3.15"' pyproject.toml &&
    grep -Fq 'def _selected_subcommand() -> str | None:' vllm/entrypoints/cli/main.py &&
    grep -Fq 'using vllm_bfloat16 = __hip_bfloat16;' csrc/cuda_vec_utils.cuh &&
    grep -Fq 'expected_hipified_path' cmake/hipify.py &&
    grep -Fq 'return on_mi3xx() or on_gfx1x()' vllm/_aiter_ops.py &&
    grep -Fq 'def torchao_version_at_least(torchao_version: str) -> bool:' \
      vllm/model_executor/layers/quantization/torchao_utils.py &&
    grep -Fq 'Hybrid models need TRITON_ATTN' vllm/platforms/rocm.py &&
    grep -Fq 'Use PyTorch top-k/top-p filtering on large-vocabulary ROCm' \
      vllm/v1/sample/ops/topk_topp_sampler.py &&
    grep -Fq 'Keep valid_count type stable across branches' \
      vllm/v1/spec_decode/utils.py &&
    grep -Fq 'def update_dflash(config_dict: dict, pre_trained_config: dict) -> None:' \
      vllm/transformers_utils/configs/speculators/algos.py &&
    grep -Fq 'def _flash_attn_uses_triton_rocm() -> bool:' \
      vllm/platforms/rocm.py &&
    grep -Fq 'def rocm_flash_attn_supports_vllm_varlen_api() -> bool:' \
      vllm/v1/attention/backends/fa_utils.py
}

_apply_all_source_patches() {
  if [[ ! -d "${srcdir}/${_vllm_srcdir}" ]]; then
    _reset_source_tree
  fi

  cd "${srcdir}/${_vllm_srcdir}"
  if _source_tree_has_all_source_patches; then
    return 0
  fi

  # Later source patches touch files changed by earlier ones, so reverse-dry-run
  # checks are not reliable on an already-patched tree. Re-extract and apply the
  # series once on a known-clean source tree whenever any sentinel is missing.
  _reset_source_tree
  cd "${srcdir}/${_vllm_srcdir}"

__PATCH_APPLY_LINES__
}

""".replace("__PATCH_VARS__", vllm_patch_vars.rstrip()).replace(
                "__PATCH_APPLY_LINES__",
                vllm_patch_apply_lines,
            )
            patch_prepare_cmds = "  _apply_all_source_patches\n"
            patch_build_cmds = "_apply_all_source_patches\n"
        build_body = f"""\
{vllm_source_prelude}{patch_helper}prepare() {{
  cd "$srcdir/${{_vllm_srcdir}}"

{patch_prepare_cmds.rstrip()}
}}

build() {{
  cd "$srcdir/${{_vllm_srcdir}}"

  {patch_build_cmds.rstrip()}

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  _strip_incompatible_lto_flags() {{
    local _value="$1"
    local _out=()
    local _token
    read -r -a _tokens <<<"${{_value}}"
    for _token in "${{_tokens[@]}}"; do
      case "${{_token}}" in
        -flto|-flto=*|-fuse-linker-plugin) ;;
        *) _out+=("${{_token}}") ;;
      esac
    done
    printf '%s' "${{_out[*]}}"
  }}

  local _debug_root="/usr/src/debug/{package_name}"
  local _prefix_map_flags="-ffile-prefix-map=${{srcdir}}=${{_debug_root}} -fdebug-prefix-map=${{srcdir}}=${{_debug_root}} -fmacro-prefix-map=${{srcdir}}=${{_debug_root}}"
  local _strix_opt_flags="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument -DGLOG_USE_GLOG_EXPORT"
  local _base_cflags="$(_strip_incompatible_lto_flags "${{CFLAGS:-}}")"
  local _base_cxxflags="$(_strip_incompatible_lto_flags "${{CXXFLAGS:-}}")"
  local _base_hipflags="$(_strip_incompatible_lto_flags "${{HIPFLAGS:-}}")"
  local _base_ldflags="$(_strip_incompatible_lto_flags "${{LDFLAGS:-}}")"
  export CFLAGS="${{_base_cflags}} ${{_prefix_map_flags}} ${{_strix_opt_flags}}"
  export CXXFLAGS="${{_base_cxxflags}} ${{_prefix_map_flags}} ${{_strix_opt_flags}}"
  export HIPFLAGS="${{_base_hipflags}} ${{_prefix_map_flags}} ${{_strix_opt_flags}}"
  export LDFLAGS="${{_base_ldflags}}"
  export CPPFLAGS="${{CPPFLAGS:-}} -DGLOG_USE_GLOG_EXPORT"
  export ROCM_HOME="/opt/rocm"
  export HIP_PATH="/opt/rocm"
  export PYTORCH_ROCM_ARCH="gfx1151"
  export CMAKE_PREFIX_PATH="/opt/rocm"
  local _hip_version
  if ! _hip_version="$(env -i PATH=/opt/rocm/bin:/usr/bin:/bin HIP_PATH=/opt/rocm ROCM_PATH=/opt/rocm /opt/rocm/bin/hipconfig --version)" || [[ -z "${{_hip_version}}" ]]; then
    echo "VLLM_HIP_VERSION_MISSING: hipconfig failed" >&2
    return 1
  fi
  export CMAKE_ARGS="-DHIP_VERSION=${{_hip_version%%-*}} ${{CMAKE_ARGS:-}}"
  export VLLM_VERSION_OVERRIDE="${{pkgver}}"
  export VLLM_ROCM_USE_AITER=1

  rm -rf .deps/triton_kernels-*

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
  cd "$srcdir/${{_vllm_srcdir}}"
  python -m installer --destdir="$pkgdir" dist/*.whl
}}"""
    elif template == "python-project-pytorch-rocm":
        upstream_version = policy_pkg["upstream_version"]
        source_patches = policy_pkg.get("source_patches", [])
        if source_patches:
            prepare_lines.extend(
                [
                    "_apply_patch_if_needed() {",
                    '  local _patch="$srcdir/$1"',
                    "",
                    '  if [[ ! -f "${_patch}" ]]; then',
                    "    printf 'missing patch file: %s\\n' \"$1\" >&2",
                    "    return 1",
                    "  fi",
                    "",
                    '  if patch --dry-run -R -Np1 -i "${_patch}" >/dev/null 2>&1; then',
                    "    return 0",
                    "  fi",
                    "",
                    '  patch -Np1 -i "${_patch}"',
                    "}",
                    "",
                ]
            )
            prepare_lines.extend(f'_apply_patch_if_needed "{patch_name}"' for patch_name in source_patches)
        prepare_lines.extend(
            [
                "# PyTorch's ROCm fork relies on vendored submodules and local hipify-generated sources.",
                'git -C "$srcdir/{src_subdir}" submodule sync --recursive'.format(src_subdir=src_subdir),
                (
                    'git -C "$srcdir/{src_subdir}" submodule update --init --recursive --force '
                    "--depth 1 --recommend-shallow"
                ).format(src_subdir=src_subdir),
            ]
        )
        build_body = f"""\
build() {{
  cd "$srcdir/{src_subdir}"
  local _install_log="$srcdir/pytorch-install.log"
  local _torch_lib="$srcdir/pytorch/torch/lib"
  local _torch_bin="$srcdir/pytorch/torch/bin"
  local _torch_include="$srcdir/pytorch/torch/include"

  # Rebuild from a fresh local CMake state so workspace moves do not poison
  # subsequent wheel builds with stale absolute paths.
  rm -rf build
  rm -rf dist "${{_torch_bin}}" "${{_torch_include}}"
  if [[ -d "${{_torch_lib}}" ]]; then
    find "${{_torch_lib}}" -mindepth 1 -maxdepth 1 ! -name libshm ! -name libshm_windows -exec rm -rf {{}} +
  fi

  local _clean_env=()
  local _env_name
  while IFS= read -r _env_name; do
    case "${{_env_name}}" in
      BASH_FUNC_*|module|ml) _clean_env+=(-u "${{_env_name}}") ;;
    esac
  done < <(compgen -e)

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  export CFLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument"
  export CXXFLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument"
  export LDFLAGS="-fuse-ld=lld"
  export PYTORCH_ROCM_ARCH="gfx1151"
  export USE_ROCM=1
  export USE_NUMPY=1
  export BLAS="OpenBLAS"
  export OpenBLAS_HOME="${{OpenBLAS_HOME:-/usr}}"
  export USE_LAPACK=1
  export USE_ROCM_CK_GEMM=1
  export AOTRITON_INSTALLED_PREFIX="/usr"
  export USE_CUDA=0
  export USE_NCCL=0
  export USE_SYSTEM_NCCL=0
  export USE_RCCL=1
  export BUILD_TEST=0
  export USE_BENCHMARK=0
  export HIP_PATH="/opt/rocm"
  export ROCM_HOME="/opt/rocm"
  export CMAKE_PREFIX_PATH="${{OpenBLAS_HOME}}:/opt/rocm"
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
  env "${{_clean_env[@]}}" CMAKE_ONLY=1 python setup.py build
  env "${{_clean_env[@]}}" cmake --build build --config Release -j "${{MAX_JOBS}}"

  if ! env "${{_clean_env[@]}}" cmake --build build --target install --config Release -j 1 >"${{_install_log}}" 2>&1; then
    grep -q '_sysconfigdata__linux_x86_64-linux-gnu.cpython-314.pyc' "${{_install_log}}" || {{
      cat "${{_install_log}}"
      return 1
    }}
  fi

  # The known install-target failure happens before CMake reaches the core
  # PyTorch developer install steps. Run the safe installers so downstream
  # C++/ROCm extension packages can build against this wheel through
  # find_package(Torch), including Torch's Caffe2 package lookup.
  env "${{_clean_env[@]}}" cmake -P build/torch/headeronly/cmake_install.cmake
  env "${{_clean_env[@]}}" cmake -P build/c10/cmake_install.cmake
  env "${{_clean_env[@]}}" cmake -P build/caffe2/cmake_install.cmake
  env "${{_clean_env[@]}}" cmake -DCMAKE_INSTALL_COMPONENT=dev -P build/cmake_install.cmake

  find "${{_torch_lib}}" -mindepth 1 -maxdepth 1 ! -name libshm ! -name libshm_windows -exec rm -rf {{}} +
  mkdir -p "${{_torch_bin}}"
  cp build/lib/lib*.so* "${{_torch_lib}}/"
  cp build/bin/torch_shm_manager build/bin/protoc-3.13.0.0 "${{_torch_bin}}/"
  ln -sf protoc-3.13.0.0 "${{_torch_bin}}/protoc"

  env "${{_clean_env[@]}}" SKIP_BUILD_DEPS=1 python setup.py bdist_wheel --dist-dir dist
}}

package() {{
  cd "$srcdir/{src_subdir}"
  local _wheel
  _wheel="$(ls dist/torch-*.whl 2>/dev/null | tail -n 1)"
  python -m installer --destdir="$pkgdir" "$_wheel"

  local _site="$pkgdir/usr/lib/python3.14/site-packages"
  local _version_py="${{_site}}/torch/version.py"
  local _hip_version _rocm_version
  if [[ ! -f "${{_version_py}}" ]]; then
    echo "PYTORCH_VERSION_METADATA_MISSING: ${{_version_py}}" >&2
    return 1
  fi
  if ! _hip_version="$(env -i PATH=/opt/rocm/bin:/usr/bin:/bin HIP_PATH=/opt/rocm ROCM_PATH=/opt/rocm /opt/rocm/bin/hipconfig --version 2>/dev/null | sed 's/-.*//')" || [[ -z "${{_hip_version}}" ]]; then
    echo "PYTORCH_HIP_VERSION_MISSING: hipconfig failed for ${{_version_py}}" >&2
    return 1
  fi
  if [[ ! -f /opt/rocm/.info/version ]]; then
    echo "PYTORCH_ROCM_VERSION_MISSING: /opt/rocm/.info/version not found for ${{_version_py}}" >&2
    return 1
  fi
  _rocm_version="$(< /opt/rocm/.info/version)"
  if [[ -z "${{_rocm_version}}" ]]; then
    echo "PYTORCH_ROCM_VERSION_EMPTY: /opt/rocm/.info/version was empty for ${{_version_py}}" >&2
    return 1
  fi
  python - "${{_version_py}}" "${{_hip_version}}" "${{_rocm_version}}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
hip = sys.argv[2]
rocm = sys.argv[3]
text = path.read_text()
text = text.replace(
    "hip: Optional[str] = None",
    f"hip: Optional[str] = {{hip!r}}",
    1,
)
text = text.replace(
    "rocm: Optional[str] = None",
    f"rocm: Optional[str] = {{rocm!r}}",
    1,
)
path.write_text(text)
PY
  grep -Fqx "hip: Optional[str] = '${{_hip_version}}'" "${{_version_py}}" || {{
    echo "PYTORCH_HIP_VERSION_REWRITE_FAILED: ${{_version_py}} _hip_version=${{_hip_version}} _rocm_version=${{_rocm_version}}" >&2
    return 1
  }}
  grep -Fqx "rocm: Optional[str] = '${{_rocm_version}}'" "${{_version_py}}" || {{
    echo "PYTORCH_ROCM_VERSION_REWRITE_FAILED: ${{_version_py}} _hip_version=${{_hip_version}} _rocm_version=${{_rocm_version}}" >&2
    return 1
  }}

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
      if ! readelf -d "${{_so}}" 2>/dev/null | grep -Eq 'libomp|libiomp5'; then
        patchelf --add-needed libomp.so "${{_so}}"
        readelf -d "${{_so}}" 2>/dev/null | grep -Eq 'libomp|libiomp5' || {{
          echo "PYTORCH_OPENMP_NEEDED_REWRITE_FAILED: ${{_so}}" >&2
          return 1
        }}
      fi
    done

    if [[ -f "${{_site}}/torch/lib/libtorch_hip.so" ]] && ! readelf -d "${{_site}}/torch/lib/libtorch_hip.so" 2>/dev/null | grep -q 'librocm_smi64'; then
      patchelf --add-needed librocm_smi64.so "${{_site}}/torch/lib/libtorch_hip.so" 2>/dev/null || true
    fi
  fi
}}"""
    elif template == "python-project-torchvision-rocm":
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
  local _debug_prefix="/usr/src/debug/{package_name}"
  local _debug_map="-ffile-prefix-map=$srcdir=${{_debug_prefix}} -fdebug-prefix-map=$srcdir=${{_debug_prefix}} -fmacro-prefix-map=$srcdir=${{_debug_prefix}}"
  export CFLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument -DGLOG_USE_GLOG_EXPORT ${{_debug_map}}"
  export CXXFLAGS="-O3 -march=native -famd-opt -Wno-error=unused-command-line-argument -DGLOG_USE_GLOG_EXPORT ${{_debug_map}}"
  export NVCC_FLAGS="${{_debug_map}}"
  export CPPFLAGS="${{CPPFLAGS:-}} -DGLOG_USE_GLOG_EXPORT"
  export ROCM_HOME="/opt/rocm"
  export ROCM_PATH="/opt/rocm"
  export HIP_ROOT_DIR="/opt/rocm"
  export PYTORCH_ROCM_ARCH="gfx1151"
  export TORCH_CUDA_ARCH_LIST=""
  export FORCE_CUDA=1
  export FORCE_MPS=0

  mkdir -p dist
  pip wheel . --no-build-isolation --no-deps --wheel-dir dist -v
}}

package() {{
  cd "$srcdir/{src_subdir}"
  local _wheel
  _wheel="$(ls dist/torchvision-*.whl 2>/dev/null | tail -n 1)"
  python -m installer --destdir="$pkgdir" "$_wheel"
  local _site
  _site="$(python - <<'PY'
import sysconfig
print(sysconfig.get_path("platlib", vars={{"base": "/usr", "platbase": "/usr"}}))
PY
)"
  local _extension="${{pkgdir}}${{_site}}/torchvision/_C.so"
  local _rpath="\\$ORIGIN:\\$ORIGIN/../torch/lib:/opt/rocm/lib"
  if [[ ! -f "${{_extension}}" ]]; then
    echo "TORCHVISION_EXTENSION_MISSING: ${{_extension}}" >&2
    return 1
  fi
  patchelf --set-rpath "${{_rpath}}" "${{_extension}}"
}}"""
    elif template == "python-project-triton-rocm":
        python_subdir = f"{src_subdir}/python"
        source_patches = policy_pkg.get("source_patches", [])
        if source_patches:
            prepare_lines.extend(
                f'patch -Np1 -i "$srcdir/{patch_name}"' for patch_name in source_patches
            )
        else:
            prepare_lines.extend(
                [
                    "# Keep Arch's Python-3.14 and setuptools compatibility deltas on top of the ROCm performance fork.",
                    "sed -i '/requires = \\[/s/.*/requires = [\"setuptools\", \"wheel\", \"pybind11>=2.13.1\"]/' python/pyproject.toml",
                    "sed -i 's/-Werror//' CMakeLists.txt",
                    "git cherry-pick -n c44b870bdd9e1ea8933fd4057b6b59a5e6e5407b || true",
                ]
            )
            rendered_recipe_patches = render_patch_prepare(
                recipe_pkg, policy_pkg.get("recipe_patch_file_rewrites")
            )
            if rendered_recipe_patches:
                prepare_lines.append(rendered_recipe_patches)
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
  export PATH="/opt/rocm/bin:${{PATH}}"
  export ROCM_HOME="/opt/rocm"
  export HIP_PATH="/opt/rocm"
  export PREBUILD_KERNELS=0
  export AITER_GPU_ARCH=gfx1151
  export SETUPTOOLS_SCM_PRETEND_VERSION="{policy_pkg['upstream_version']}"
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
  rm -f dist/*.whl
  pip wheel . --no-build-isolation --no-deps --wheel-dir dist -v
}}

package() {{
  cd "$srcdir/{src_subdir}"
  python -m installer --destdir="$pkgdir" dist/*.whl
}}"""
    elif template == "rust-wheel-pypi":
        for patch_name in policy_pkg.get("source_patches", []):
            prepare_lines.extend(
                [
                    f'if ! patch --dry-run -R -Np1 -i "$srcdir/{patch_name}" >/dev/null 2>&1; then',
                    f'  patch -Np1 -i "$srcdir/{patch_name}"',
                    "fi",
                ]
            )
        build_body = f"""\
build() {{
  cd "$srcdir/{src_subdir}"

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  local _debug_prefix="/usr/src/debug/{package_name}"
  export CARGO_HOME="$srcdir/.cargo"
  mkdir -p "$CARGO_HOME"
  export CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER="$CC"
  export RUSTFLAGS="-C target-cpu=znver5 -C opt-level=3 --remap-path-prefix=$srcdir=${{_debug_prefix}}"
  unset CFLAGS CXXFLAGS LDFLAGS

  python -m build --wheel --no-isolation
}}

package() {{
  cd "$srcdir/{src_subdir}"
  python -m installer --destdir="$pkgdir" dist/*.whl

  local _debug_prefix="/usr/src/debug/{package_name}"
  find "$pkgdir/usr/lib" -type f -path '*/sboms/*.json' -print0 | while IFS= read -r -d '' _file; do
    sed -i \
      -e "s|$srcdir/{src_subdir}|${{_debug_prefix}}/{src_subdir}|g" \
      -e "s|$srcdir|${{_debug_prefix}}|g" \
      -e "s|/tmp/pkg/src/{src_subdir}|${{_debug_prefix}}/{src_subdir}|g" \
      "$_file" 2>/dev/null || true
  done
}}"""
    elif template == "python-project-torchao":
        prepare_lines.extend(
            [
                "if [[ ! -d third_party/cutlass/include ]]; then",
                "  git submodule sync --recursive",
                "  git submodule update --init --recursive",
                "fi",
                "",
            ]
        )
        for patch_name in policy_pkg.get("source_patches", []):
            prepare_lines.extend(
                [
                    f'if ! patch --dry-run -R -Np1 -i "$srcdir/{patch_name}" >/dev/null 2>&1; then',
                    f'  patch -Np1 -i "$srcdir/{patch_name}"',
                    "fi",
                ]
            )
        build_body = f"""\
build() {{
  cd "$srcdir/{src_subdir}"

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  local _base_flags="-O3 -march=native -mprefer-vector-width=512 -mavx512f -mavx512dq -mavx512vl -mavx512bw -mllvm -enable-gvn-hoist -mllvm -enable-gvn-sink -famd-opt -Wno-error=unused-command-line-argument"
  local _wheel_flags
  _wheel_flags="$(printf '%s' "${{_base_flags}}" | sed -E 's/-mllvm (-[^ ]+)/-Xclang -mllvm -Xclang \\1/g; s/  +/ /g; s/^ +| +$//g')"
  local _base_cflags="${{CFLAGS:-}}"
  local _base_cxxflags="${{CXXFLAGS:-}}"
  local _base_ldflags="${{LDFLAGS:-}}"

  export CFLAGS="${{_base_cflags:+${{_base_cflags}} }}${{_wheel_flags}}"
  export CXXFLAGS="${{_base_cxxflags:+${{_base_cxxflags}} }}${{_wheel_flags}}"
  export LDFLAGS="${{_base_ldflags:+${{_base_ldflags}} }}-famd-opt"
  export ROCM_HOME=/opt/rocm
  export PYTORCH_ROCM_ARCH=gfx1151
  export VERSION_SUFFIX=

  python -m build --wheel --no-isolation
}}

package() {{
  cd "$srcdir/{src_subdir}"
  python -m installer --destdir="$pkgdir" dist/*.whl

  local _rpath='$ORIGIN:$ORIGIN/../torch/lib:/opt/rocm/lib'
  local _so
  shopt -s nullglob
  for _so in "$pkgdir"/usr/lib/python3.14/site-packages/torchao/_C*.so; do
    patchelf --set-rpath "${{_rpath}}" "${{_so}}"
  done
  shopt -u nullglob
}}"""
    elif template == "native-wheel-pypi":
        for patch_name in policy_pkg.get("source_patches", []):
            prepare_lines.extend(
                [
                    f'if ! patch --dry-run -R -Np1 -i "$srcdir/{patch_name}" >/dev/null 2>&1; then',
                    f'  patch -Np1 -i "$srcdir/{patch_name}"',
                    "fi",
                ]
            )
        config_settings = policy_pkg.get("build_config_settings", [])
        build_flags = ["--wheel", "--no-isolation"]
        if policy_pkg.get("skip_dependency_check"):
            build_flags.append("--skip-dependency-check")
        build_command_head = "python -m build " + " ".join(build_flags)
        if config_settings:
            build_command_lines = [f"{build_command_head} \\"]
            for idx, setting in enumerate(config_settings):
                suffix = " \\" if idx < len(config_settings) - 1 else ""
                build_command_lines.append(f"    -C{shell_quote(setting)}{suffix}")
            build_command = "\n".join(build_command_lines)
        else:
            build_command = build_command_head
        build_env_lines = []
        for assignment in policy_pkg.get("build_env", []):
            name, value = assignment.split("=", 1)
            build_env_lines.append(f"export {name}={shell_quote(value)}")
        build_env_exports = "\n".join(build_env_lines)
        if build_env_exports:
            build_env_exports = "\n" + textwrap.indent(build_env_exports, "  ") + "\n"
        single_wheel_install = policy_pkg.get("single_wheel_install", False)
        clean_build_outputs = "\n  rm -rf dist build" if single_wheel_install else ""
        if single_wheel_install:
            installer_command = "\n".join([
                "local _wheels=(dist/*.whl)",
                "  if (( $" + "{#_wheels[@]} != 1 )); then",
                "    printf 'expected exactly one wheel, found %s\\n' \"$" + "{#_wheels[@]}\" >&2",
                "    return 1",
                "  fi",
                "  python -m installer --destdir=\"$pkgdir\" \"$" + "{_wheels[0]}\"",
            ])
        else:
            installer_command = "python -m installer --destdir=\"$pkgdir\" dist/*.whl"
        build_body = f"""\
build() {{
  cd "$srcdir/{src_subdir}"

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  local _base_flags="-O3 -march=native -mprefer-vector-width=512 -mavx512f -mavx512dq -mavx512vl -mavx512bw -mllvm -enable-gvn-hoist -mllvm -enable-gvn-sink -famd-opt -Wno-error=unused-command-line-argument"
  local _wheel_flags
  _wheel_flags="$(printf '%s' "${{_base_flags}}" | sed -E 's/-mllvm (-[^ ]+)/-Xclang -mllvm -Xclang \\1/g; s/  +/ /g; s/^ +| +$//g')"
  local _base_cflags="${{CFLAGS:-}}"
  local _base_cxxflags="${{CXXFLAGS:-}}"
  local _base_ldflags="${{LDFLAGS:-}}"

  export CFLAGS="${{_base_cflags:+${{_base_cflags}} }}${{_wheel_flags}}"
  export CXXFLAGS="${{_base_cxxflags:+${{_base_cxxflags}} }}${{_wheel_flags}}"
  export LDFLAGS="${{_base_ldflags:+${{_base_ldflags}} }}-famd-opt"{build_env_exports}
{clean_build_outputs}
  {build_command}
}}

package() {{
  cd "$srcdir/{src_subdir}"
  {installer_command}
}}"""
    elif template == "python-project-torch-migraphx":
        for patch_name in policy_pkg.get("source_patches", []):
            prepare_lines.extend(
                [
                    f'if ! patch --dry-run -R -Np1 -i "$srcdir/{patch_name}" >/dev/null 2>&1; then',
                    f'  patch -Np1 -i "$srcdir/{patch_name}"',
                    "fi",
                ]
            )
        build_body = f"""\
build() {{
  cd "$srcdir/{src_subdir}/py"

  {compiler_env_snippet(compiler_root)}  _setup_compiler_env
  export CFLAGS="-O3 -march=native -mprefer-vector-width=512 -mavx512f -mavx512dq -mavx512vl -mavx512bw -Wno-error=unused-command-line-argument"
  export CXXFLAGS="${{CFLAGS}}"
  export ROCM_HOME=/opt/rocm
  export HIP_PATH=/opt/rocm
  export PYTORCH_ROCM_ARCH=gfx1151

  python -m build --wheel --no-isolation
}}

package() {{
  cd "$srcdir/{src_subdir}/py"

  python -m installer --destdir="$pkgdir" dist/*.whl

  local _site="$pkgdir/usr/lib/python3.14/site-packages"
  local _rpath='$ORIGIN:$ORIGIN/torch/lib:/opt/rocm/lib'
  patchelf --set-rpath "${{_rpath}}" "${{_site}}"/_torch_migraphx*.so
  install -Dm644 "$srcdir/{src_subdir}/LICENSE" \\
    "$pkgdir/usr/share/licenses/{package_name}/LICENSE"
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
            textwrap.indent("\n".join(line for line in prepare_lines if line), "  "),
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

    pkgrel = int(policy_pkg.get("pkgrel", preserved_pkgrel(package_name, version)))
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


def normalize_recipe_patches(
    recipe_patches: list[dict],
    file_rewrites: dict[str, str] | None = None,
) -> list[dict]:
    normalized: list[dict] = []
    file_rewrites = file_rewrites or {}
    for patch in recipe_patches:
        item = dict(patch)
        if item.get("file") in file_rewrites:
            item["file"] = file_rewrites[item["file"]]
        if item.get("patch") in file_rewrites:
            item["patch"] = file_rewrites[item["patch"]]
        if (
            item.get("type") == "file_copy"
            and item.get("dst") == "${VLLM_DIR}/.venv/bin/cmake"
            and item.get("src") == "system cmake binary"
        ):
            item["description"] = (
                "Replace the recipe's broken venv-local Python cmake wrapper "
                "with the real system cmake binary. The cmake pip package "
                "installs a Python wrapper that does `from cmake import "
                "cmake`, which fails inside pip's build isolation where the "
                "cmake Python module is unavailable.\n"
            )
            item["dst"] = "<build-venv>/.venv/bin/cmake"
            item["src"] = "/usr/bin/cmake"
        normalized.append(item)
    return normalized


def renders_recipe_patch_actions(policy_pkg: dict) -> bool:
    if policy_pkg.get("source_patches_replace_recipe_patches"):
        return False
    if policy_pkg.get("source_patches"):
        return False
    return policy_pkg.get("template") in {"scons-aocl-libm", "python-project-triton-rocm"}


def rendered_patch_count(policy_pkg: dict, recipe_pkg: dict) -> int:
    source_patch_count = len(policy_pkg.get("source_patches", []))
    if source_patch_count:
        return source_patch_count
    if not renders_recipe_patch_actions(policy_pkg):
        return 0
    return len(recipe_pkg.get("patches", []))


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
    rendered_policy = dict(policy_pkg)
    rendered_policy.pop("source_patches", None)
    rendered_policy.pop("recipe_branch_override", None)
    source_patches = policy_pkg.get("source_patches", [])
    source_patch_sha256sums = []
    if source_patches and not policy_pkg.get("extra_sources"):
        source_patch_sha256sums = policy_pkg.get("extra_sha256sums", [])
        rendered_policy.pop("extra_sha256sums", None)
    recipe_branch = policy_pkg.get("recipe_branch_override", recipe_pkg.get("branch"))
    recipe_patches = []
    if renders_recipe_patch_actions(policy_pkg):
        recipe_patches = normalize_recipe_patches(
            recipe_pkg.get("patches", []),
            policy_pkg.get("recipe_patch_file_rewrites"),
        )
    payload = {
        "name": package_name,
        "package_name": package_name,
        "pkgver": version,
        "policy": rendered_policy,
        "recipe": {
            "repo": recipe_pkg.get("repo"),
            "branch": recipe_branch,
            "src_dir": recipe_pkg.get("src_dir"),
            "method": recipe_pkg.get("method"),
            "phase": recipe_pkg.get("phase"),
            "steps": recipe_pkg.get("steps", []),
            "depends_on": recipe_pkg.get("depends_on", []),
            "notes": recipe_notes,
            "patches": recipe_patches,
        },
        "provenance": defaults,
    }
    payload["maintenance"] = {
        "authoritative_reference": authoritative_reference,
        "advisory_references": advisory_references,
        "divergence_notes": policy_pkg.get("divergence_notes", []),
        "update_notes": policy_pkg.get("update_notes", []),
        "source_patches": source_patches,
    }
    if source_patch_sha256sums:
        payload["maintenance"]["source_patch_sha256sums"] = source_patch_sha256sums
    role = package_role(package_name, policy_pkg)
    if role:
        payload["role"] = role
    backends = optional_backends(package_name, policy_pkg)
    if backends:
        payload["optional_backends"] = backends
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def render_readme(package_name: str, policy_pkg: dict, recipe_pkg: dict, version: str, defaults: dict) -> str:
    notes = policy_pkg.get("scaffold_notes", [])
    recipe_notes = policy_pkg.get("recipe_notes_override", recipe_pkg.get("notes", "").strip())
    patch_count = rendered_patch_count(policy_pkg, recipe_pkg)
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

    recipe_revision_text = "unknown"
    if defaults.get("recipe_commit") and defaults.get("recipe_date"):
        recipe_revision_text = f"{defaults['recipe_commit']} ({defaults['recipe_date']}"
        if defaults.get("recipe_history_count") is not None:
            recipe_revision_text += f", {defaults['recipe_history_count']} commits touching recipe path"
        recipe_revision_text += ")"

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
        f"- Upstream repo: `{policy_pkg.get('repo') or recipe_pkg.get('repo') or policy_pkg.get('url', '')}`",
        f"- Package version: `{version}`",
        f"- Recipe revision: `{recipe_revision_text}`",
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
            "- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.",
            "- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.",
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
    try:
        recipe_root = resolve_recipe_root(args.recipe_root, packaging_root=packaging_root)
        recipe_dir = resolve_recipe_dir(recipe_root, args.recipe_subdir)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 2

    policy = load_toml(policy_path)
    defaults = dict(policy.get("defaults", {}))
    recipe_manifest = load_recipe_manifest(recipe_dir)
    defaults.update(recipe_revision(recipe_root, args.recipe_subdir))
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
        version = policy_pkg["upstream_version"]
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
            render_readme(package_name, policy_pkg, recipe_pkg, version, defaults),
            encoding="utf-8",
        )
        print(f"rendered {package_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
