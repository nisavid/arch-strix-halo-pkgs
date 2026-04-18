#!/usr/bin/env zsh

set -euo pipefail

autoload -Uz colors
colors

typeset -gr SCRIPT_PATH=${(%):-%N}
typeset -gr SCRIPT_DIR=${SCRIPT_PATH:A:h}
typeset -gr REPO_ROOT=${SCRIPT_DIR:h}
typeset -gr DEFAULT_PACKAGES_ROOT=${REPO_ROOT}/packages
typeset -gr DEFAULT_REPO_DIR=${REPO_ROOT}/repo/x86_64
typeset -gr DEFAULT_PUBLISH_ROOT=${PUBLISH_ROOT:-/srv/pacman/strix-halo-gfx1151/x86_64}

typeset -g SUDO_KEEPALIVE_PID=""

function timestamp_now() {
  emulate -L zsh
  print -r -- ${(%):-%D{%Y%m%dT%H%M%S}}
}

function is_interactive_tty() {
  [[ -t 0 && -t 1 ]]
}

function die() {
  emulate -L zsh
  local message=$1
  local code=${2:-1}
  print -u2 -P "%F{1}${message}%f"
  return ${code}
}

function note() {
  emulate -L zsh
  print -P "%F{6}${1}%f"
}

function warn() {
  emulate -L zsh
  print -u2 -P "%F{3}${1}%f"
}

function ensure_run_logging() {
  emulate -L zsh
  local run_root=$1
  local run_log=${run_root}/run.log
  mkdir -p ${run_root}
  exec > >(tee -a ${run_log}) 2>&1
}

function start_sudo_keepalive() {
  emulate -L zsh
  sudo -v
  (
    while true; do
      sudo -n true
      sleep 30
    done
  ) &
  SUDO_KEEPALIVE_PID=$!
}

function stop_sudo_keepalive() {
  emulate -L zsh
  if [[ -n ${SUDO_KEEPALIVE_PID} ]]; then
    kill ${SUDO_KEEPALIVE_PID} 2>/dev/null || true
    wait ${SUDO_KEEPALIVE_PID} 2>/dev/null || true
    SUDO_KEEPALIVE_PID=""
  fi
}

function cleanup() {
  emulate -L zsh
  stop_sudo_keepalive
}

function prompt_install_scope() {
  emulate -L zsh
  local reply
  print -P "%F{6}Choose install scope:%f"
  print "1) Installed Repo Packages"
  print "2) All Repo Packages"
  print "3) Select Specific Packages"
  read -r "reply?Selection: "
  case ${reply} in
    1) print -r -- installed ;;
    2) print -r -- all ;;
    3) print -r -- specific ;;
    *) die "INVALID_INSTALL_SCOPE_SELECTION" 2 ;;
  esac
}

function prompt_specific_outputs() {
  emulate -L zsh
  local graph_file=$1
  local -a outputs
  outputs=("${(@f)$(graph_query ${graph_file} all_outputs)}")
  if (( ${#outputs} == 0 )); then
    die "NO_REPO_OUTPUTS_AVAILABLE" 2
    return $?
  fi
  local index=1
  for output in ${outputs[@]}; do
    print "${index}) ${output}"
    (( index += 1 ))
  done
  local selection
  read -r "selection?Choose package numbers (comma separated): "
  local -a chosen=()
  local raw
  for raw in ${(s:,:)selection}; do
    local trimmed=${raw//[[:space:]]/}
    [[ -n ${trimmed} ]] || continue
    if [[ ${trimmed} != <-> ]] || (( trimmed < 1 || trimmed > ${#outputs} )); then
      die "INVALID_PACKAGE_SELECTION: ${trimmed}" 2
      return $?
    fi
    chosen+=(${outputs[trimmed]})
  done
  if (( ${#chosen} == 0 )); then
    die "NO_PACKAGES_SELECTED" 2
    return $?
  fi
  print -r -- ${chosen[@]}
}

function load_graph_json() {
  emulate -L zsh
  local packages_root=$1
  shift
  python ${REPO_ROOT}/tools/repo_package_graph.py --json --packages-root ${packages_root} "$@"
}

function graph_query() {
  emulate -L zsh
  local graph_file=$1
  local mode=$2
  local key=${3-}
  python - ${graph_file} ${mode} ${key} <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

graph_file = Path(sys.argv[1])
mode = sys.argv[2]
key = sys.argv[3] if len(sys.argv) > 3 else ""
payload = json.loads(graph_file.read_text())
roots = {item["root_name"]: item for item in payload["roots"]}

if mode == "build_order":
    for root_name in payload["build_order"]:
        print(root_name)
elif mode == "all_outputs":
    outputs = sorted(
        output
        for item in payload["roots"]
        for output in item["outputs"]
    )
    for output in outputs:
        print(output)
elif mode == "root_package_dir":
    print(roots[key]["package_dir"])
elif mode == "root_outputs":
    for output in roots[key]["outputs"]:
        print(output)
elif mode == "root_bootstrap_outputs":
    root = roots[key]
    repo_outputs = {
        output
        for item in payload["roots"]
        for output in item["outputs"]
    }
    for output in [*root["depends"], *root["makedepends"]]:
        if output in repo_outputs:
            print(output)
else:
    raise SystemExit(f"UNKNOWN_GRAPH_QUERY_MODE: {mode}")
PY
}

function currently_installed_repo_outputs() {
  emulate -L zsh
  local graph_file=$1
  local -A repo_outputs=()
  local output
  for output in "${(@f)$(graph_query ${graph_file} all_outputs)}"; do
    repo_outputs[${output}]=1
  done
  local installed
  for installed in "${(@f)$(pacman -Qq)}"; do
    if [[ -n ${repo_outputs[${installed}]-} ]]; then
      print -r -- ${installed}
    fi
  done
}

function render_plan_json() {
  emulate -L zsh
  local graph_file=$1
  local install_scope=$2
  local run_root=$3
  shift 3
  python - ${graph_file} ${install_scope} ${run_root} "$@" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

graph_file = Path(sys.argv[1])
install_scope = sys.argv[2]
run_root = sys.argv[3]
selected_outputs = sys.argv[4:]
payload = json.loads(graph_file.read_text())
print(
    json.dumps(
        {
            "install_scope": install_scope,
            "planned_run_root": run_root,
            "build_order": payload["build_order"],
            "selected_install_outputs": selected_outputs,
        },
        indent=2,
        sort_keys=True,
    )
)
PY
}

function write_json_array() {
  emulate -L zsh
  local destination=$1
  shift
  python - ${destination} "$@" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

destination = Path(sys.argv[1])
items = sys.argv[2:]
destination.write_text(json.dumps(items, indent=2, sort_keys=False) + "\n", encoding="utf-8")
PY
}

function publish_repo_dir() {
  emulate -L zsh
  local repo_dir=$1
  local publish_root=$2
  sudo install -d ${publish_root}
  sudo rsync -a --delete ${repo_dir}/ ${publish_root}/
}

function install_outputs() {
  emulate -L zsh
  local -a outputs=("$@")
  (( ${#outputs} > 0 )) || return 0
  sudo pacman -Sy --noconfirm ${outputs[@]}
}

function build_root() {
  emulate -L zsh
  local package_dir=$1
  (
    cd ${package_dir}
    makepkg -sf --noconfirm
  )
}

function select_install_outputs() {
  emulate -L zsh
  local graph_file=$1
  local install_scope=$2
  shift 2
  case ${install_scope} in
    explicit|specific)
      print -l -- "$@"
      ;;
    installed)
      currently_installed_repo_outputs ${graph_file}
      ;;
    all)
      graph_query ${graph_file} all_outputs
      ;;
    *)
      die "UNKNOWN_INSTALL_SCOPE: ${install_scope}" 2
      return $?
      ;;
  esac
}

function main() {
  emulate -L zsh
  setopt pipefail
  trap cleanup EXIT INT TERM

  local dry_run=0
  local packages_root=${DEFAULT_PACKAGES_ROOT}
  local repo_dir=${DEFAULT_REPO_DIR}
  local publish_root=${DEFAULT_PUBLISH_ROOT}
  local install_scope=""
  local -a explicit_targets=()

  while (( $# > 0 )); do
    case $1 in
      --dry-run)
        dry_run=1
        ;;
      --packages-root)
        shift
        packages_root=${1-}
        ;;
      --repo-dir)
        shift
        repo_dir=${1-}
        ;;
      --publish-root)
        shift
        publish_root=${1-}
        ;;
      --install-scope)
        shift
        install_scope=${1-}
        ;;
      --help)
        print "usage: rebuild_publish_install.zsh [--dry-run] [--packages-root PATH] [--repo-dir PATH] [--publish-root PATH] [--install-scope installed|all] [package ...]"
        return 0
        ;;
      *)
        explicit_targets+=($1)
        ;;
    esac
    shift
  done

  if (( ${#explicit_targets} > 0 )); then
    if [[ -n ${install_scope} ]]; then
      die "EXPLICIT_TARGETS_CONFLICT_WITH_INSTALL_SCOPE" 2
      return $?
    fi
    install_scope=explicit
  elif [[ -z ${install_scope} ]]; then
    if is_interactive_tty; then
      install_scope=$(prompt_install_scope)
    else
      die "INSTALL_SCOPE_REQUIRED: choose --install-scope, pass package targets, or run interactively" 2
      return $?
    fi
  fi

  local graph_json
  graph_json=$(load_graph_json ${packages_root} ${explicit_targets[@]})
  local graph_file
  graph_file=$(mktemp)
  print -r -- ${graph_json} > ${graph_file}

  local -a selected_install_outputs
  if [[ ${install_scope} == specific ]]; then
    selected_install_outputs=("${(@s: :)$(prompt_specific_outputs ${graph_file})}")
    install_scope=explicit
  else
    selected_install_outputs=("${(@f)$(select_install_outputs ${graph_file} ${install_scope} ${explicit_targets[@]})}")
  fi

  local run_root=${REPO_ROOT}/docs/worklog/rebuild-install-runs/$(timestamp_now)
  if (( dry_run )); then
    render_plan_json ${graph_file} ${install_scope} ${run_root} ${selected_install_outputs[@]}
    rm -f ${graph_file}
    return 0
  fi

  ensure_run_logging ${run_root}
  note "repo_root=${REPO_ROOT}"
  note "run_root=${run_root}"
  note "install_scope=${install_scope}"
  write_json_array ${run_root}/selected-install-scope.json ${selected_install_outputs[@]}
  print -r -- "${(@f)$(graph_query ${graph_file} build_order)}" > ${run_root}/build-order.txt

  mkdir -p ${repo_dir}
  start_sudo_keepalive

  local -A installed_bootstrap_outputs=()
  local root_name
  for root_name in "${(@f)$(graph_query ${graph_file} build_order)}"; do
    local -a bootstrap_outputs=()
    local bootstrap_output
    for bootstrap_output in "${(@f)$(graph_query ${graph_file} root_bootstrap_outputs ${root_name})}"; do
      [[ -n ${installed_bootstrap_outputs[${bootstrap_output}]-} ]] && continue
      bootstrap_outputs+=(${bootstrap_output})
      installed_bootstrap_outputs[${bootstrap_output}]=1
    done
    if (( ${#bootstrap_outputs} > 0 )); then
      note "bootstrap install: ${bootstrap_outputs[*]}"
      install_outputs ${bootstrap_outputs[@]}
    fi

    local package_dir
    package_dir=$(graph_query ${graph_file} root_package_dir ${root_name})
    note "building ${root_name} in ${package_dir}"
    build_root ${package_dir}

    python ${REPO_ROOT}/tools/update_pacman_repo.py \
      --package-dir ${package_dir} \
      --repo-dir ${repo_dir} \
      --recursive
    publish_repo_dir ${repo_dir} ${publish_root}
  done

  if (( ${#selected_install_outputs} > 0 )); then
    note "final install: ${selected_install_outputs[*]}"
    install_outputs ${selected_install_outputs[@]}
  else
    warn "no selected install outputs resolved for scope=${install_scope}"
  fi

  print -r -- ${selected_install_outputs[@]} | tr ' ' '\n' > ${run_root}/published-packages.txt
  note "REBUILD_INSTALL_OK"
  rm -f ${graph_file}
}

main "$@"
