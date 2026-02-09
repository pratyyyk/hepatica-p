#!/usr/bin/env bash
set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PYTHON_BIN="${PYTHON_BIN:-python3}"
readonly REQUIRE_DOCKER="${REQUIRE_DOCKER:-false}"

step() {
  echo
  echo "==> $1"
}

step "Backend tests"
(
  cd "${ROOT_DIR}/backend"
  "${PYTHON_BIN}" -m pytest -q
)

step "Backend smoke flow"
(
  cd "${ROOT_DIR}/backend"
  make smoke
)

step "Frontend checks"
(
  cd "${ROOT_DIR}/frontend"
  npm ci
  npm run lint
  npm audit --omit=dev --audit-level=high
  npm run build
)

step "Infra validation"
(
  cd "${ROOT_DIR}/infra"
  ./scripts/validate.sh
)

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  step "Backend container build"
  docker build -t hepatica-backend:preflight "${ROOT_DIR}/backend"
elif [[ "${REQUIRE_DOCKER}" == "true" ]]; then
  echo "Docker daemon is unavailable and REQUIRE_DOCKER=true." >&2
  exit 1
else
  echo
  echo "==> Backend container build"
  echo "Skipped: docker daemon is unavailable."
fi

echo
echo "Release preflight passed."
