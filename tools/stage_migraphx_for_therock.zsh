#!/usr/bin/env zsh

emulate -R zsh
setopt err_exit pipe_fail no_unset

typeset -r REPO_ROOT=${0:A:h:h}
typeset stage=/tmp/therock-migraphx-stage
typeset src=/tmp/AMDMIGraphX
typeset rocm_root=/opt/rocm
typeset jobs=${$(nproc 2>/dev/null):-1}
typeset targets=gfx1151
typeset migraphx_ref=b69836e6c97de179a80d764d24574edba7ba1b1b
typeset protobuf_dir=/usr/lib/cmake/protobuf
typeset protobuf_soname=libprotobuf.so.36.1.0
typeset utf8_validity_soname=libutf8_validity.so.36.1.0
typeset abseil_soversion=2608.0.0
# migraphx-gfx1151 7.13.0-4 ships 14 regular ELF files; the payload gate
# fails a stage in which it finds fewer.
typeset migraphx_min_elfs=14
typeset clean=0
typeset deploy=0
typeset skip_build=0
typeset with_composable_kernel=0
typeset with_mlir=0

usage() {
  cat <<'EOF'
usage: tools/stage_migraphx_for_therock.zsh [options]

Build AMDMIGraphX into a staged /opt/rocm root, render therock-gfx1151 from it,
preview the amerge plan, and optionally deploy the refreshed package family.

Options:
  --stage PATH       staged filesystem root (default: /tmp/therock-migraphx-stage)
  --src PATH         AMDMIGraphX checkout path (default: /tmp/AMDMIGraphX)
  --rocm-root PATH   installed ROCm tree that seeds the stage and provides
                     the compilers (default: /opt/rocm)
  --targets VALUE    GPU target list passed as -DGPU_TARGETS (default: gfx1151)
  --migraphx-ref REF AMDMIGraphX commit to build
                     (default: b69836e6c97de179a80d764d24574edba7ba1b1b)
  --protobuf-dir PATH
                     protobuf CMake config directory used for AMDMIGraphX
                     ONNX parsing; its lib directory must also hold the
                     matching Abseil libraries and cmake/absl
                     (default: /usr/lib/cmake/protobuf)
  -j, --jobs N       parallel build jobs (default: nproc)
  --clean            remove the stage and source dirs before starting
  --skip-build       reuse an existing source build and only install/render/deploy
  --with-ck          enable AMDMIGraphX Composable Kernel integration
  --with-mlir        enable AMDMIGraphX rocMLIR integration
  --deploy           run the privileged amerge deployment after preview
  -h, --help         show this help

Typical:
  tools/stage_migraphx_for_therock.zsh --clean
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

# Set reply to the DT_NEEDED sonames of one ELF file.
read_needed() {
  emulate -L zsh
  local lib=$1
  local dynamic
  dynamic=$(LC_ALL=C readelf -d $lib) || fail "readelf cannot read $lib"
  reply=(${(M)${(f)dynamic}:#*Shared library: \[*\]})
  reply=(${${reply#*Shared library: \[}%\]*})
}

require_cmds() {
  emulate -L zsh
  local cmd
  for cmd in git rsync cmake ninja python readelf; do
    command -v $cmd >/dev/null 2>&1 || fail "missing required command: $cmd"
  done
}

clean_path() {
  emulate -L zsh
  local target_path=$1
  [[ -n $target_path ]] || fail "refusing to remove empty path"
  [[ $target_path == /tmp/* ]] || fail "refusing to clean non-/tmp path: $target_path"
  run rm -rf -- $target_path
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

  status "patching AMDMIGraphX no-MLIR build stubs for the staged root"
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

replace_once("""#include <migraphx/gpu/prepare_mlir.hpp>
#include <mlir-c/Dialect/RockEnums.h>
#include <numeric>
""", """#include <migraphx/gpu/prepare_mlir.hpp>
#ifdef MIGRAPHX_MLIR
#include <mlir-c/Dialect/RockEnums.h>
#endif
#include <numeric>
""")

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

copy_current_rocm_into_stage() {
  emulate -L zsh
  [[ -d $rocm_root ]] || fail "ROCm root is missing: $rocm_root"
  status "copying current $rocm_root into $stage"
  run mkdir -p $stage/opt
  run rsync -aH --no-owner --no-group --delete $rocm_root/ $stage/opt/rocm/
}

build_and_install_migraphx() {
  emulate -L zsh
  local disable_versions
  disable_versions=$(python_disable_versions)
  local pybind11_dir
  pybind11_dir=$(python -m pybind11 --cmakedir)
  local protobuf_lib_dir=${protobuf_dir%/cmake/protobuf}
  local protobuf_prefix=${protobuf_lib_dir:h}
  local absl_dir=$protobuf_lib_dir/cmake/absl
  local ck=OFF
  local mlir=OFF
  (( with_composable_kernel )) && ck=ON
  (( with_mlir )) && mlir=ON
  [[ -d $protobuf_dir ]] || fail "protobuf CMake config directory is missing: $protobuf_dir"
  [[ $protobuf_lib_dir != $protobuf_dir ]] || fail "protobuf CMake config directory must end with /cmake/protobuf: $protobuf_dir"
  [[ -f $protobuf_lib_dir/libprotobuf.so ]] || fail "protobuf library is missing: $protobuf_lib_dir/libprotobuf.so"
  [[ -f $protobuf_lib_dir/libutf8_validity.so ]] || fail "utf8 validity library is missing: $protobuf_lib_dir/libutf8_validity.so"
  [[ $(read_soname $protobuf_lib_dir/libprotobuf.so) == $protobuf_soname ]] || fail "protobuf SONAME must be $protobuf_soname"
  [[ $(read_soname $protobuf_lib_dir/libutf8_validity.so) == $utf8_validity_soname ]] || fail "utf8 validity SONAME must be $utf8_validity_soname"
  [[ -d $absl_dir ]] || fail "Abseil CMake config directory is missing: $absl_dir"
  [[ -f $protobuf_lib_dir/libabsl_base.so ]] || fail "Abseil library is missing: $protobuf_lib_dir/libabsl_base.so"
  [[ $(read_soname $protobuf_lib_dir/libabsl_base.so) == libabsl_base.so.$abseil_soversion ]] || fail "Abseil SONAME must be libabsl_base.so.$abseil_soversion"
  local -a configure_args=(
    -S $src
    -B $src/build
    -G Ninja
    -DCMAKE_BUILD_TYPE=Release
    -DCMAKE_INSTALL_PREFIX=/opt/rocm
    "-DCMAKE_PREFIX_PATH=$protobuf_prefix;$stage/opt/rocm;$rocm_root"
    -Dprotobuf_DIR=$protobuf_dir
    -Dabsl_DIR=$absl_dir
    -Dpybind11_DIR=$pybind11_dir
    -DCMAKE_C_COMPILER=$rocm_root/lib/llvm/bin/amdclang
    -DCMAKE_CXX_COMPILER=$rocm_root/lib/llvm/bin/amdclang++
    -DGPU_TARGETS=$targets
    -DMIGRAPHX_ENABLE_PYTHON=ON
    -DMIGRAPHX_USE_COMPOSABLEKERNEL=$ck
    -DMIGRAPHX_ENABLE_MLIR=$mlir
    -DROCM_ENABLE_CLANG_TIDY=OFF
    -DPYTHON_DISABLE_VERSIONS=$disable_versions
  )

  status "configuring AMDMIGraphX for $targets"
  run cmake $configure_args

  status "building and installing AMDMIGraphX into $stage"
  run env LD_LIBRARY_PATH=$protobuf_lib_dir:${LD_LIBRARY_PATH-} \
    DESTDIR=$stage \
    cmake --build $src/build --target install -j$jobs
}

# Print, one per line and relative to the stage, every regular file (not a
# symlink) under the policy's scan roots that policies/therock-packages.toml
# assigns to the named split package and that starts with the ELF magic. The
# render classifies the stage with the same generator and policy, so this is
# every regular ELF the package will ship, whatever its name.
list_staged_package_elfs() {
  emulate -L zsh
  local package=$1
  python - $REPO_ROOT $stage $package <<'PY'
import sys
from pathlib import Path

repo_root, root, package = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.dont_write_bytecode = True
sys.path.insert(0, str(repo_root / "generators"))
import therock_split

policy = therock_split.load_policy(repo_root / "policies/therock-packages.toml")
classifier = therock_split.Classifier(policy)
for relpath in therock_split.walk_scan_roots(root, policy["repo"]["scan_roots"]):
    path = root / relpath
    if path.is_symlink() or not path.is_file():
        continue
    if classifier.classify(relpath) != package:
        continue
    with path.open("rb") as fh:
        if fh.read(4) == b"\x7fELF":
            print(relpath)
PY
}

validate_stage() {
  emulate -L zsh
  local protobuf_lib_dir=${protobuf_dir%/cmake/protobuf}
  status "checking staged MIGraphX payload"
  # Every regular ELF that migraphx-gfx1151 will ship, chosen by package
  # ownership and ELF magic rather than by name. The package's symlinks
  # resolve to these files.
  local listing
  listing=$(list_staged_package_elfs migraphx-gfx1151) \
    || fail "cannot list the staged migraphx-gfx1151 ELF files"
  local -a payload=(${(f)listing})
  (( $#payload )) || fail "staged root still has no MIGraphX payload"
  print -rl -- $payload
  (( $#payload >= migraphx_min_elfs )) \
    || fail "staged migraphx-gfx1151 payload has $#payload regular ELF files; expected at least $migraphx_min_elfs"
  status "checking the DT_NEEDED entries of $#payload staged migraphx-gfx1151 ELF files"

  # Pacman sees protobuf and Abseil only through the pinned libprotobuf.so
  # provide and the versioned abseil-cpp range, so every regular ELF the
  # package ships, not only the parsers, may link only the pinned sonames.
  local elf
  local -a unpinned
  for elf in $payload; do
    read_needed $stage/$elf
    unpinned=(
      ${${(M)reply:#libprotobuf.so*}:#$protobuf_soname}
      ${${(M)reply:#libutf8_validity.so*}:#$utf8_validity_soname}
      ${${(M)reply:#libabsl_*}:#*.so.$abseil_soversion}
    )
    if (( $#unpinned )); then
      print -u2 "staged $elf links: ${(j:, :)unpinned}"
      fail "staged MIGraphX payload links protobuf, utf8_validity, or Abseil other than $protobuf_soname, $utf8_validity_soname, and libabsl_*.so.$abseil_soversion"
    fi
  done

  local -a parser_libs=(
    $stage/opt/rocm/lib/migraphx/lib/libmigraphx_onnx.so
    $stage/opt/rocm/lib/migraphx/lib/libmigraphx_tf.so
  )

  local -a abseil_needed
  local parser_lib
  for parser_lib in $parser_libs; do
    [[ -f $parser_lib ]] || fail "missing staged MIGraphX parser library: $parser_lib"
    read_needed $parser_lib

    if (( ! ${reply[(I)$protobuf_soname]} )); then
      print -u2 "staged ${parser_lib:t} needs: ${(j:, :)reply}"
      fail "staged MIGraphX parser library is not linked against $protobuf_soname"
    fi

    if (( ! ${reply[(I)$utf8_validity_soname]} )); then
      print -u2 "staged ${parser_lib:t} needs: ${(j:, :)reply}"
      fail "staged MIGraphX parser library is not linked against $utf8_validity_soname"
    fi

    abseil_needed=(${(M)reply:#libabsl_*})
    if (( ! $#abseil_needed )); then
      print -u2 "staged ${parser_lib:t} needs: ${(j:, :)reply}"
      fail "staged MIGraphX parser library links no Abseil libraries; expected libabsl_*.so.$abseil_soversion"
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
    --rocm-root)
      shift
      (( $# )) || fail "--rocm-root needs a path"
      rocm_root=$1
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

if (( clean )); then
  clean_path $stage
  clean_path $src
fi

if (( skip_build )); then
  [[ -d $src/build ]] || fail "--skip-build needs an existing build dir: $src/build"
  copy_current_rocm_into_stage
  status "installing existing AMDMIGraphX build into $stage"
  run env LD_LIBRARY_PATH=${protobuf_dir%/cmake/protobuf}:${LD_LIBRARY_PATH-} \
    DESTDIR=$stage \
    cmake --build $src/build --target install -j$jobs
else
  copy_current_rocm_into_stage
  clone_or_update_source
  patch_migraphx_source_for_staged_root
  build_and_install_migraphx
fi

validate_stage
render_and_deploy
