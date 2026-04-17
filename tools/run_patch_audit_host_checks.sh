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
  find "${pkgdir}" -maxdepth 1 -type f -name '*.pkg.tar.*' \
    ! -name '*.db.tar.*' ! -name '*.files.tar.*' \
    | sort | tail -n 1
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

aiter_pkg="$(latest_pkg "${repo_root}/packages/python-amd-aiter-gfx1151")"
vllm_pkg="$(latest_pkg "${repo_root}/packages/python-vllm-rocm-gfx1151")"

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
run sudo pacman -S --needed python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151
run pacman -Qi python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151

run python -m vllm --version
run python "${repo_root}/tools/gemma4_text_smoke.py" "${model}"
run python "${repo_root}/tools/gemma4_server_smoke.py" \
  "${model}" \
  --mode basic \
  --server-log "${server_log}"

printf '\nPATCH_AUDIT_HOST_CHECK_OK\n'
printf 'main_log=%s\n' "${main_log}"
printf 'server_log=%s\n' "${server_log}"
