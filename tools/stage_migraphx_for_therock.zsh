#!/usr/bin/env zsh

emulate -R zsh
setopt err_exit pipe_fail no_unset

typeset -r REPO_ROOT=${0:A:h:h}
typeset stage=${THEROCK_STAGE_ROOT-}
typeset src=/tmp/AMDMIGraphX
typeset jobs=${$(nproc 2>/dev/null):-1}
typeset targets=gfx1151
# AMDMIGraphX 2.16.1: release/rocm-rel-7.14 head, the MIGraphX release for ROCm 7.14.1.
typeset migraphx_ref=2487b688c453b9007ac69ff1d79ad6cf9b509901
# Isolated protobuf/Abseil prefix for the ONNX and TF parsers. The pins are the
# Arch extra packages that the host upgrades to in the same transaction as the
# rebuilt migraphx-gfx1151; the sha256 values come from the Arch sync database.
typeset protobuf_prefix=/tmp/migraphx-protobuf-prefix
typeset protobuf_pkg_dir=
typeset protobuf_dir=
typeset -r arch_archive=https://archive.archlinux.org/packages
typeset -ra protobuf_pkgs=(
  "p/protobuf/protobuf-36.1-1-x86_64.pkg.tar.zst 3d63417c8fbe2354bea29b23c338baf3f03c9438e0127c5519d6dddc4825185c"
  "a/abseil-cpp/abseil-cpp-20260817.0-2-x86_64.pkg.tar.zst 4ecd2e4e2cf7096edfad8522df68d0d9adbe41ce7a6689c1915905342ae6a016"
)
typeset protobuf_soname=
typeset utf8_validity_soname=
typeset absl_soname_suffix=
typeset rocm_cmake_compat=
typeset clean=0
typeset deploy=0
typeset skip_build=0
typeset with_composable_kernel=0
typeset with_mlir=0

usage() {
  cat <<'EOF'
usage: tools/stage_migraphx_for_therock.zsh [options]

Build AMDMIGraphX into a staged TheRock root, render therock-gfx1151 from it,
preview the amerge plan, and optionally deploy the refreshed package family.

The stage must already hold the TheRock payload: run
tools/stage_therock_payload.py --stage PATH first. MIGraphX is configured
against that stage only, with the stage's own amdclang and no host /opt/rocm
fallback, and installed into it with DESTDIR.

Options:
  --stage PATH       staged filesystem root holding opt/rocm
                     (default: $THEROCK_STAGE_ROOT)
  --src PATH         AMDMIGraphX checkout path (default: /tmp/AMDMIGraphX)
  --targets VALUE    GPU target list passed as -DGPU_TARGETS (default: gfx1151)
  --migraphx-ref REF AMDMIGraphX commit to fetch and build
                     (default: 2487b688c453b9007ac69ff1d79ad6cf9b509901, 2.16.1)
  --protobuf-prefix PATH
                     isolated protobuf 36.1 / abseil-cpp 20260817 prefix,
                     populated from the pinned Arch packages when empty
                     (default: /tmp/migraphx-protobuf-prefix)
  --protobuf-pkg-dir PATH
                     download cache for the pinned Arch packages
                     (default: <protobuf-prefix>.pkgs)
  --protobuf-dir PATH
                     use this protobuf CMake config directory instead of the
                     isolated prefix; it must end with /cmake/protobuf
  -j, --jobs N       parallel build jobs (default: nproc)
  --clean            remove the source checkout and the protobuf prefix before
                     starting; the stage and the package cache are kept
  --skip-build       reuse an existing source build and only install/render/deploy
  --with-ck          enable AMDMIGraphX Composable Kernel integration
  --with-mlir        enable AMDMIGraphX rocMLIR integration
  --deploy           run the privileged amerge deployment after preview
  -h, --help         show this help

Typical:
  tools/stage_migraphx_for_therock.zsh --stage <stage> --clean
EOF
}

fail() {
  print -u2 -P "%F{red}error:%f $*"
  exit 2
}

status() {
  print -P "%F{cyan}==>%f $*"
}

run() {
  print -P "%F{blue}$%f ${(q-)@}"
  "$@" || fail "command failed: ${(q-)@}"
}

read_soname() {
  emulate -L zsh
  local lib=$1
  readelf -d $lib | sed -n 's/.*Library soname: \[\([^]]*\)\].*/\1/p'
}

read_needed() {
  emulate -L zsh
  local lib=$1
  readelf -d $lib | sed -n 's/.*Shared library: \[\([^]]*\)\].*/\1/p'
}

require_cmds() {
  emulate -L zsh
  local cmd
  for cmd in git cmake ninja python find readelf curl bsdtar sha256sum; do
    command -v $cmd >/dev/null 2>&1 || fail "missing required command: $cmd"
  done
}

clean_path() {
  emulate -L zsh
  local target_path=${1:A}
  [[ -n $1 ]] || fail "refusing to remove empty path"
  [[ $target_path == /?*/?* ]] || fail "refusing to clean a top-level path: $target_path"
  [[ $target_path != ${HOME:A} && $target_path != ${stage:A} ]] || fail "refusing to clean: $target_path"
  [[ $target_path != ${REPO_ROOT:A} && $target_path != ${REPO_ROOT:A}/* ]] || fail "refusing to clean inside the repo: $target_path"
  run rm -rf -- $target_path
}

require_stage() {
  emulate -L zsh
  [[ -n $stage ]] || fail "pass --stage or set THEROCK_STAGE_ROOT"
  stage=${stage:A}
  local rocm=$stage/opt/rocm
  [[ -f $rocm/.info/version ]] || fail "no staged TheRock payload at $rocm; run tools/stage_therock_payload.py --stage $stage"
  [[ -x $rocm/lib/llvm/bin/amdclang++ ]] || fail "staged TheRock compiler is missing: $rocm/lib/llvm/bin/amdclang++"
  status "using staged TheRock $(<$rocm/.info/version) at $rocm"
}

python_disable_versions() {
  emulate -L zsh
  local current
  current=$(python - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)
  local -a versions=(3.6 3.7 3.8 3.9 3.10 3.11 3.12 3.13 3.14)
  local -a disabled=()
  local version
  for version in $versions; do
    [[ $version == $current ]] || disabled+=($version)
  done
  print -r -- ${(j:;:)disabled}
}

prepare_protobuf_prefix() {
  emulate -L zsh
  if [[ -n $protobuf_dir ]]; then
    status "using protobuf CMake config at $protobuf_dir"
    return
  fi
  protobuf_prefix=${protobuf_prefix:A}
  protobuf_dir=$protobuf_prefix/usr/lib/cmake/protobuf
  if [[ -d $protobuf_dir ]]; then
    status "reusing isolated protobuf prefix at $protobuf_prefix"
    return
  fi

  local pkg_dir=${protobuf_pkg_dir:-$protobuf_prefix.pkgs}
  run mkdir -p $pkg_dir
  local entry rel sha file actual
  local -a pkg_files=()
  for entry in $protobuf_pkgs; do
    rel=${entry%% *}
    sha=${entry##* }
    file=$pkg_dir/${rel:t}
    if [[ ! -f $file ]]; then
      status "downloading ${rel:t}"
      run curl -fL --retry 3 -o $file.part $arch_archive/$rel
      run mv -- $file.part $file
    fi
    actual=$(sha256sum $file)
    actual=${actual%% *}
    [[ $actual == $sha ]] || fail "sha256 mismatch for $file: got $actual, pinned $sha"
    pkg_files+=($file)
  done

  status "populating isolated protobuf prefix at $protobuf_prefix"
  run mkdir -p $protobuf_prefix
  local pkg
  for pkg in $pkg_files; do
    run bsdtar -xf $pkg -C $protobuf_prefix \
      --exclude .PKGINFO --exclude .BUILDINFO --exclude .MTREE --exclude .INSTALL
  done
  [[ -d $protobuf_dir ]] || fail "protobuf CMake config directory is missing after extraction: $protobuf_dir"
}

derive_protobuf_sonames() {
  emulate -L zsh
  local protobuf_lib_dir=${protobuf_dir%/cmake/protobuf}
  [[ -d $protobuf_dir ]] || fail "protobuf CMake config directory is missing: $protobuf_dir"
  [[ $protobuf_lib_dir != $protobuf_dir ]] || fail "protobuf CMake config directory must end with /cmake/protobuf: $protobuf_dir"
  [[ -f $protobuf_lib_dir/libprotobuf.so ]] || fail "protobuf library is missing: $protobuf_lib_dir/libprotobuf.so"
  [[ -f $protobuf_lib_dir/libutf8_validity.so ]] || fail "utf8 validity library is missing: $protobuf_lib_dir/libutf8_validity.so"
  protobuf_soname=$(read_soname $protobuf_lib_dir/libprotobuf.so)
  utf8_validity_soname=$(read_soname $protobuf_lib_dir/libutf8_validity.so)
  [[ $protobuf_soname == libprotobuf.so.?* ]] || fail "cannot read the protobuf SONAME from $protobuf_lib_dir/libprotobuf.so"
  [[ $utf8_validity_soname == libutf8_validity.so.?* ]] || fail "cannot read the utf8 validity SONAME from $protobuf_lib_dir/libutf8_validity.so"
  if [[ -f $protobuf_lib_dir/libabsl_base.so ]]; then
    local absl_soname
    absl_soname=$(read_soname $protobuf_lib_dir/libabsl_base.so)
    absl_soname_suffix=${absl_soname#libabsl_base.so.}
  fi
  status "building against $protobuf_soname, $utf8_validity_soname${absl_soname_suffix:+, Abseil .so.$absl_soname_suffix}"
}

clone_or_update_source() {
  emulate -L zsh
  if [[ ! -d $src/.git ]]; then
    [[ ! -e $src ]] || fail "AMDMIGraphX source path exists without a Git checkout: $src"
    status "initializing AMDMIGraphX checkout at $src"
    run git init $src
    run git -C $src remote add origin https://github.com/ROCm/AMDMIGraphX.git
  fi
  status "fetching AMDMIGraphX revision $migraphx_ref"
  run git -C $src fetch --depth 1 origin $migraphx_ref
  run git -C $src checkout --detach FETCH_HEAD
}

patch_migraphx_source_for_staged_root() {
  emulate -L zsh
  (( with_mlir )) && return

  local mlir_cpp=$src/src/targets/gpu/mlir.cpp
  [[ -f $mlir_cpp ]] || fail "missing AMDMIGraphX source file: $mlir_cpp"

  # AMDMIGraphX 2.16 already guards the rocMLIR RockEnums.h include with
  # MIGRAPHX_MLIR (upstream #4962), but its no-MLIR branch still lacks
  # definitions for four functions that mlir.hpp exports unconditionally.
  status "adding AMDMIGraphX no-MLIR build stubs"
  run python - $mlir_cpp <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

def replace_once(old: str, new: str) -> None:
    global text
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"expected MLIR source block not found in {path}")
    text = text.replace(old, new, 1)

replace_once("""std::string dump_mlir(module m, const std::vector<shape>& inputs)
{
    use(m);
    use(inputs);
    return {};
}

// Disabling clang-tidy warning on non-real useage.
""", """std::string dump_mlir(module m, const std::vector<shape>& inputs)
{
    use(m);
    use(inputs);
    return {};
}

void dump_mlir_to_file(module m, const std::vector<shape>& inputs, const fs::path& location)
{
    use(m);
    use(inputs);
    use(location);
}

bool is_module_fusible(const module& m, const context& migraphx_ctx, const value& solution)
{
    use(m);
    use(migraphx_ctx);
    use(solution);
    return false;
}

void adjust_param_shapes(module& m, const std::vector<shape>& inputs)
{
    use(m);
    use(inputs);
}

void dump_mlir_to_mxr(module m, const std::vector<instruction_ref>& inputs, const fs::path& location)
{
    use(m);
    use(inputs);
    use(location);
}

// Disabling clang-tidy warning on non-real useage.
""")

path.write_text(text)
PY
}

write_rocm_cmake_compat() {
  emulate -L zsh
  local rocm_cmake_dir=$stage/opt/rocm/share/rocmcmakebuildtools/cmake
  rocm_cmake_compat=
  [[ -d $rocm_cmake_dir ]] || fail "staged rocm-cmake modules are missing: $rocm_cmake_dir"
  grep -q 'function(rocm_add_version_resource' $rocm_cmake_dir/*.cmake && return

  # AMDMIGraphX 2.16 calls rocm_add_version_resource, which its pinned
  # rocm-cmake (1d4652ae) defines, but the rocm-cmake 0.14.0 that TheRock
  # 7.14.1 ships predates it. The upstream function only writes a Windows .rc
  # version resource under if(WIN32), so it is a no-op on Linux. Define that
  # no-op before project() modules load; a stage rocm-cmake that defines the
  # function would replace it on include.
  rocm_cmake_compat=$src/.ashp/rocm-cmake-compat.cmake
  status "adding the Linux no-op rocm_add_version_resource that the staged rocm-cmake lacks"
  run mkdir -p ${rocm_cmake_compat:h}
  print -r -- 'function(rocm_add_version_resource TARGET NAME DESCRIPTION)
endfunction()' >| $rocm_cmake_compat
}

build_and_install_migraphx() {
  emulate -L zsh
  local rocm=$stage/opt/rocm
  local disable_versions
  disable_versions=$(python_disable_versions)
  local pybind11_dir
  pybind11_dir=$(python -m pybind11 --cmakedir)
  local protobuf_lib_dir=${protobuf_dir%/cmake/protobuf}
  local protobuf_prefix_root=${protobuf_lib_dir:h}
  local ck=OFF
  local mlir=OFF
  (( with_composable_kernel )) && ck=ON
  (( with_mlir )) && mlir=ON
  local -a configure_args=(
    -S $src
    -B $src/build
    -G Ninja
    -DCMAKE_BUILD_TYPE=Release
    -DCMAKE_INSTALL_PREFIX=/opt/rocm
    "-DCMAKE_PREFIX_PATH=$protobuf_prefix_root;$rocm"
    -Dprotobuf_DIR=$protobuf_dir
    -Dpybind11_DIR=$pybind11_dir
    -DCMAKE_C_COMPILER=$rocm/lib/llvm/bin/amdclang
    -DCMAKE_CXX_COMPILER=$rocm/lib/llvm/bin/amdclang++
    -DGPU_TARGETS=$targets
    -DMIGRAPHX_ENABLE_PYTHON=ON
    -DMIGRAPHX_USE_COMPOSABLEKERNEL=$ck
    -DMIGRAPHX_ENABLE_MLIR=$mlir
    -DROCM_ENABLE_CLANG_TIDY=OFF
    -DPYTHON_DISABLE_VERSIONS=$disable_versions
  )
  [[ -z $rocm_cmake_compat ]] || configure_args+=(-DCMAKE_PROJECT_INCLUDE=$rocm_cmake_compat)
  local -a build_env=(
    ROCM_PATH=$rocm
    HIP_PATH=$rocm
    LD_LIBRARY_PATH=$protobuf_lib_dir:${LD_LIBRARY_PATH-}
  )

  status "configuring AMDMIGraphX $migraphx_ref for $targets against $rocm"
  run env $build_env cmake $configure_args

  status "building and installing AMDMIGraphX into $stage"
  run env $build_env DESTDIR=$stage cmake --build $src/build --target install -j$jobs
}

install_existing_build() {
  emulate -L zsh
  local rocm=$stage/opt/rocm
  local protobuf_lib_dir=${protobuf_dir%/cmake/protobuf}
  status "installing existing AMDMIGraphX build into $stage"
  run env ROCM_PATH=$rocm HIP_PATH=$rocm \
    LD_LIBRARY_PATH=$protobuf_lib_dir:${LD_LIBRARY_PATH-} \
    DESTDIR=$stage \
    cmake --build $src/build --target install -j$jobs
}

validate_stage() {
  emulate -L zsh
  local protobuf_lib_dir=${protobuf_dir%/cmake/protobuf}
  status "checking staged MIGraphX payload"
  run find $stage/opt/rocm \( \
    -name migraphx-driver -o \
    -name 'libmigraphx*.so*' -o \
    -name 'migraphx.cpython-*.so' \
  \) -print

  local found_count
  found_count=$(find $stage/opt/rocm \( \
    -name migraphx-driver -o \
    -name 'libmigraphx*.so*' -o \
    -name 'migraphx.cpython-*.so' \
  \) -print | wc -l)
  (( found_count > 0 )) || fail "staged root still has no MIGraphX payload"

  local -a parser_libs=(
    $stage/opt/rocm/lib/migraphx/lib/libmigraphx_onnx.so
    $stage/opt/rocm/lib/migraphx/lib/libmigraphx_tf.so
  )

  local -a needed stale
  local parser_lib dep
  for parser_lib in $parser_libs; do
    [[ -f $parser_lib ]] || fail "missing staged MIGraphX parser library: $parser_lib"
    needed=("${(@f)$(read_needed $parser_lib)}")
    stale=()
    for dep in $needed; do
      case $dep in
        libprotobuf.so.*) [[ $dep == $protobuf_soname ]] || stale+=($dep) ;;
        libutf8_validity.so.*) [[ $dep == $utf8_validity_soname ]] || stale+=($dep) ;;
        libabsl_*.so.*) [[ -z $absl_soname_suffix || $dep == *.so.$absl_soname_suffix ]] || stale+=($dep) ;;
      esac
    done
    if (( $#stale )); then
      print -u2 "staged ${parser_lib:t} needs: ${(j:, :)needed}"
      fail "staged MIGraphX parser library links a protobuf ABI other than the build target: ${(j:, :)stale}"
    fi

    if (( ! ${needed[(I)$protobuf_soname]} )); then
      print -u2 "staged ${parser_lib:t} needs: ${(j:, :)needed}"
      fail "staged MIGraphX parser library is not linked against $protobuf_soname"
    fi

    if (( ! ${needed[(I)$utf8_validity_soname]} )); then
      print -u2 "staged ${parser_lib:t} needs: ${(j:, :)needed}"
      fail "staged MIGraphX parser library is not linked against $utf8_validity_soname"
    fi
  done

  status "checking staged Python import"
  run env LD_LIBRARY_PATH=$protobuf_lib_dir:$stage/opt/rocm/lib:${LD_LIBRARY_PATH-} \
    PYTHONPATH=$stage/opt/rocm/lib \
    python - <<'PY'
import migraphx
print(migraphx.__file__)
PY
}

render_and_deploy() {
  emulate -L zsh
  cd $REPO_ROOT
  status "rendering therock-gfx1151 from $stage"
  run python tools/render_therock_pkgbase.py --therock-root $stage

  status "previewing amerge plan"
  run env _THEROCK_ROOT=$stage tools/amerge run therock-gfx1151 --dry-run --preview=tree --color=never

  if (( deploy )); then
    status "deploying therock-gfx1151"
    run env _THEROCK_ROOT=$stage tools/amerge run therock-gfx1151
    status "checking installed MIGraphX import"
    run python - <<'PY'
import migraphx
print(migraphx.__file__)
PY
  else
    print -P "%F{yellow}preview only:%f rerun with --deploy to publish and install"
  fi
}

while (( $# )); do
  case $1 in
    --stage)
      shift
      (( $# )) || fail "--stage needs a path"
      stage=$1
      ;;
    --src)
      shift
      (( $# )) || fail "--src needs a path"
      src=$1
      ;;
    --targets)
      shift
      (( $# )) || fail "--targets needs a value"
      targets=$1
      ;;
    --migraphx-ref)
      shift
      (( $# )) || fail "--migraphx-ref needs a value"
      migraphx_ref=$1
      ;;
    --protobuf-prefix)
      shift
      (( $# )) || fail "--protobuf-prefix needs a path"
      protobuf_prefix=$1
      ;;
    --protobuf-pkg-dir)
      shift
      (( $# )) || fail "--protobuf-pkg-dir needs a path"
      protobuf_pkg_dir=$1
      ;;
    --protobuf-dir)
      shift
      (( $# )) || fail "--protobuf-dir needs a path"
      protobuf_dir=$1
      ;;
    -j|--jobs)
      shift
      (( $# )) || fail "--jobs needs a value"
      jobs=$1
      ;;
    --clean)
      clean=1
      ;;
    --skip-build)
      skip_build=1
      ;;
    --with-ck)
      with_composable_kernel=1
      ;;
    --with-mlir)
      with_mlir=1
      ;;
    --deploy)
      deploy=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
  shift
done

require_cmds
cd $REPO_ROOT
require_stage

if (( clean )); then
  clean_path $src
  [[ -n $protobuf_dir ]] || clean_path $protobuf_prefix
fi

if (( skip_build )); then
  [[ -d $src/build ]] || fail "--skip-build needs an existing build dir: $src/build"
fi

prepare_protobuf_prefix
derive_protobuf_sonames

if (( skip_build )); then
  install_existing_build
else
  clone_or_update_source
  patch_migraphx_source_for_staged_root
  write_rocm_cmake_compat
  build_and_install_migraphx
fi

validate_stage
render_and_deploy
