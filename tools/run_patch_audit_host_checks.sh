#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
model="${1:-google/gemma-4-26B-A4B-it}"
publish_root="${PUBLISH_ROOT:-/srv/pacman/strix-halo-gfx1151/x86_64}"
timestamp="$(date +%Y%m%dT%H%M%S)"
run_root="${repo_root}/docs/worklog/patch-audit-final-checks/${timestamp}"
main_log="${run_root}/host-checks.log"
server_log="${run_root}/gemma4-server.log"

mkdir -p "${run_root}"
exec > >(tee -a "${main_log}") 2>&1

run() {
  printf '\n[%s] %s\n' "$(date --iso-8601=seconds)" "$*"
  "$@"
}

latest_pkg() {
  local pkgdir="$1"
  local pkgname="$2"
  python "${repo_root}/tools/select_latest_package.py" \
    --package-dir "${pkgdir}" \
    --pkgname "${pkgname}"
}

amd_smi_bin() {
  if command -v amd-smi >/dev/null 2>&1; then
    command -v amd-smi
    return 0
  fi
  if [[ -x /opt/rocm/bin/amd-smi ]]; then
    printf '%s\n' /opt/rocm/bin/amd-smi
    return 0
  fi
  return 1
}

log_gpu_processes() {
  local amd_smi
  if ! amd_smi="$(amd_smi_bin)"; then
    echo "gpu_processes_unavailable: amd-smi not found"
    return 0
  fi
  run "${amd_smi}" process -G --json
}

ensure_no_stale_vllm_engine_cores() {
  local stale
  stale="$(
    ps -eo pid=,ppid=,etimes=,comm=,cmd= \
      | awk '$4 == "VLLM::EngineCore" {print}'
  )"
  if [[ -z "${stale}" ]]; then
    return 0
  fi
  echo "preexisting stale VLLM::EngineCore processes detected:" >&2
  printf '%s\n' "${stale}" >&2
  echo "PATCH_AUDIT_HOST_CHECK_FAILED: kill the preexisting stale VLLM::EngineCore process(es) above and rerun." >&2
  exit 3
}

printf 'repo_root=%s\n' "${repo_root}"
printf 'run_root=%s\n' "${run_root}"
printf 'main_log=%s\n' "${main_log}"
printf 'server_log=%s\n' "${server_log}"
printf 'model=%s\n' "${model}"

run git -C "${repo_root}" rev-parse HEAD
run git -C "${repo_root}" submodule status -- upstream/ai-notes
run python --version
run uname -a

aiter_pkg="$(latest_pkg "${repo_root}/packages/python-amd-aiter-gfx1151" python-amd-aiter-gfx1151)"
vllm_pkg="$(latest_pkg "${repo_root}/packages/python-vllm-rocm-gfx1151" python-vllm-rocm-gfx1151)"

if [[ -z "${aiter_pkg}" || -z "${vllm_pkg}" ]]; then
  echo "PATCH_AUDIT_HOST_CHECK_FAILED: expected built package archives for python-amd-aiter-gfx1151 and python-vllm-rocm-gfx1151" >&2
  echo "HINT: build those package directories first, then re-run this script." >&2
  exit 2
fi

printf 'aiter_pkg=%s\n' "${aiter_pkg}"
printf 'vllm_pkg=%s\n' "${vllm_pkg}"

run python "${repo_root}/tools/update_pacman_repo.py" \
  --package-dir "${repo_root}/packages/python-amd-aiter-gfx1151" \
  --repo-dir "${repo_root}/repo/x86_64"
run python "${repo_root}/tools/update_pacman_repo.py" \
  --package-dir "${repo_root}/packages/python-vllm-rocm-gfx1151" \
  --repo-dir "${repo_root}/repo/x86_64"

run sudo install -d "${publish_root}"
run sudo rsync -a --delete "${repo_root}/repo/x86_64/" "${publish_root}/"
run sudo pacman -Sy
run sudo pacman -S python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151
run pacman -Qi python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151

log_gpu_processes
ensure_no_stale_vllm_engine_cores

run vllm --version
run python "${repo_root}/tools/gemma4_text_smoke.py" "${model}"
run python "${repo_root}/tools/gemma4_server_smoke.py" \
  "${model}" \
  --mode basic \
  --server-log "${server_log}"

log_gpu_processes

printf '\nPATCH_AUDIT_HOST_CHECK_OK\n'
printf 'main_log=%s\n' "${main_log}"
printf 'server_log=%s\n' "${server_log}"
