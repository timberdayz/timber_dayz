#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${1:-$(pwd)}"
OUTPUT_PATH="${2:-${PROJECT_ROOT}/temp/deploy_bundle.tgz}"
BUNDLE_DIR="${PROJECT_ROOT}/temp/deploy_bundle"

rm -rf "${BUNDLE_DIR}"
rm -f "${OUTPUT_PATH}"

mkdir -p \
  "${BUNDLE_DIR}" \
  "${BUNDLE_DIR}/config" \
  "${BUNDLE_DIR}/sql/init" \
  "${BUNDLE_DIR}/nginx"

copy_if_exists() {
  local src="$1"
  local dest="$2"

  if [ ! -e "${src}" ]; then
    return 0
  fi

  mkdir -p "$(dirname "${dest}")"
  cp "${src}" "${dest}"
}

cd "${PROJECT_ROOT}"

copy_if_exists "docker-compose.yml" "${BUNDLE_DIR}/docker-compose.yml"
copy_if_exists "docker-compose.prod.yml" "${BUNDLE_DIR}/docker-compose.prod.yml"
copy_if_exists "docker-compose.cloud.yml" "${BUNDLE_DIR}/docker-compose.cloud.yml"
copy_if_exists "docker-compose.cloud-4c8g.yml" "${BUNDLE_DIR}/docker-compose.cloud-4c8g.yml"
copy_if_exists "scripts/deploy_remote_production.sh" "${BUNDLE_DIR}/deploy_remote_production.sh"

shopt -s nullglob

for file in config/*.yaml config/*.py; do
  base_name="$(basename "${file}")"
  if [ "${base_name}" = "metabase_config.yaml" ]; then
    continue
  fi
  copy_if_exists "${file}" "${BUNDLE_DIR}/config/${base_name}"
done

for file in sql/init/*.sql; do
  copy_if_exists "${file}" "${BUNDLE_DIR}/sql/init/$(basename "${file}")"
done

copy_if_exists "nginx/nginx.prod.conf" "${BUNDLE_DIR}/nginx/nginx.prod.conf"

tar -czf "${OUTPUT_PATH}" -C "${BUNDLE_DIR}" .

echo "${OUTPUT_PATH}"
