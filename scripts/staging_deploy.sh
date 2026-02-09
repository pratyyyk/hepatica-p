#!/usr/bin/env bash
set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly INFRA_DIR="${ROOT_DIR}/infra"

MODE="plan"
AUTO_APPROVE="false"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/staging_deploy.sh [--plan] [--apply] [--auto-approve]

Modes:
  --plan          Run terraform validate + plan (default)
  --apply         Run terraform validate + apply
  --auto-approve  Use -auto-approve during apply
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan)
      MODE="plan"
      shift
      ;;
    --apply)
      MODE="apply"
      shift
      ;;
    --auto-approve)
      AUTO_APPROVE="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

step() {
  echo
  echo "==> $1"
}

step "Check AWS auth"
aws sts get-caller-identity >/dev/null

if [[ ! -f "${INFRA_DIR}/terraform.tfvars" ]]; then
  echo "Missing ${INFRA_DIR}/terraform.tfvars. Copy and fill terraform.tfvars.example first." >&2
  exit 1
fi

step "Validate terraform configuration"
(
  cd "${INFRA_DIR}"
  ./scripts/validate.sh
)

step "Terraform plan"
terraform -chdir="${INFRA_DIR}" plan -input=false

if [[ "${MODE}" == "apply" ]]; then
  step "Terraform apply"
  if [[ "${AUTO_APPROVE}" == "true" ]]; then
    terraform -chdir="${INFRA_DIR}" apply -input=false -auto-approve
  else
    terraform -chdir="${INFRA_DIR}" apply -input=false
  fi

  step "Fetch service outputs"
  OUTPUT_JSON="$(terraform -chdir="${INFRA_DIR}" output -json)"
  BACKEND_URL="$(printf '%s' "${OUTPUT_JSON}" | python3 -c 'import json,sys; data=json.load(sys.stdin); print((data.get("backend_service_url") or {}).get("value") or "")')"
  FRONTEND_URL="$(printf '%s' "${OUTPUT_JSON}" | python3 -c 'import json,sys; data=json.load(sys.stdin); print((data.get("frontend_service_url") or {}).get("value") or "")')"

  if [[ -n "${BACKEND_URL}" ]]; then
    step "Backend health check"
    curl -fsSL "${BACKEND_URL}/healthz" >/dev/null
    echo "Backend healthy: ${BACKEND_URL}/healthz"
  else
    echo "Backend service URL is not set in terraform outputs."
  fi

  if [[ -n "${FRONTEND_URL}" ]]; then
    step "Frontend health check"
    curl -fsSL "${FRONTEND_URL}" >/dev/null
    echo "Frontend reachable: ${FRONTEND_URL}"
  else
    echo "Frontend service URL is not set in terraform outputs."
  fi
fi

echo
echo "Staging deploy script completed (${MODE})."
