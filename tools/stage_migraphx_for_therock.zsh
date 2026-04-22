#!/usr/bin/env zsh

emulate -R zsh
setopt err_exit pipe_fail no_unset

typeset -r REPO_ROOT=${0:A:h:h}
typeset stage=/tmp/therock-migraphx-stage
typeset src=/tmp/AMDMIGraphX
typeset jobs=${$(nproc 2>/dev/null):-1}
typeset targets=gfx1151
typeset clean=0
typeset deploy=0
typeset skip_build=0

usage() {
  cat <<'EOF'
usage: tools/stage_migraphx_for_therock.zsh [options]

Build AMDMIGraphX into a staged /opt/rocm root, render therock-gfx1151 from it,
preview the amerge plan, and optionally deploy the refreshed package family.

Options:
  --stage PATH       staged filesystem root (default: /tmp/therock-migraphx-stage)
  --src PATH         AMDMIGraphX checkout path (default: /tmp/AMDMIGraphX)
  --targets VALUE    GPU target list passed as -DGPU_TARGETS (default: gfx1151)
  -j, --jobs N       parallel build jobs (default: nproc)
  --clean            remove the stage and source dirs before starting
  --skip-build       reuse an existing source build and only install/render/deploy
  --deploy           run the privileged amerge deployment after preview
  -h, --help         show this help

Typical:
  tools/stage_migraphx_for_therock.zsh --clean --deploy
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
  "$@"
}

require_cmds() {
  emulate -L zsh
  local cmd
  for cmd in git rsync cmake ninja python find; do
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
  if [[ -d $src/.git ]]; then
    status "updating AMDMIGraphX checkout at $src"
    run git -C $src fetch --depth 1 origin develop
    run git -C $src checkout --detach FETCH_HEAD
  else
    status "cloning AMDMIGraphX into $src"
    run git clone --depth 1 --branch develop https://github.com/ROCm/AMDMIGraphX.git $src
  fi
}

copy_current_rocm_into_stage() {
  emulate -L zsh
  [[ -d /opt/rocm ]] || fail "/opt/rocm is missing"
  status "copying current /opt/rocm into $stage"
  run mkdir -p $stage/opt
  run rsync -aH --delete /opt/rocm/ $stage/opt/rocm/
}

build_and_install_migraphx() {
  emulate -L zsh
  local disable_versions
  disable_versions=$(python_disable_versions)

  status "configuring AMDMIGraphX for $targets"
  run cmake -S $src -B $src/build -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/opt/rocm \
    "-DCMAKE_PREFIX_PATH=$stage/opt/rocm;/opt/rocm" \
    -DCMAKE_C_COMPILER=/opt/rocm/lib/llvm/bin/amdclang \
    -DCMAKE_CXX_COMPILER=/opt/rocm/lib/llvm/bin/amdclang++ \
    -DGPU_TARGETS=$targets \
    -DMIGRAPHX_ENABLE_PYTHON=ON \
    -DPYTHON_DISABLE_VERSIONS=$disable_versions

  status "building AMDMIGraphX"
  run cmake --build $src/build -j$jobs

  status "installing AMDMIGraphX into $stage"
  env DESTDIR=$stage cmake --install $src/build
}

validate_stage() {
  emulate -L zsh
  status "checking staged MIGraphX payload"
  find $stage/opt/rocm \( \
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

  status "checking staged Python import"
  env LD_LIBRARY_PATH=$stage/opt/rocm/lib:${LD_LIBRARY_PATH-} \
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
  env _THEROCK_ROOT=$stage tools/amerge run therock-gfx1151 --preview=tree --color=never

  if (( deploy )); then
    status "deploying therock-gfx1151"
    env _THEROCK_ROOT=$stage tools/amerge run therock-gfx1151
    status "checking installed MIGraphX import"
    python - <<'PY'
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
  env DESTDIR=$stage cmake --install $src/build
else
  copy_current_rocm_into_stage
  clone_or_update_source
  build_and_install_migraphx
fi

validate_stage
render_and_deploy
