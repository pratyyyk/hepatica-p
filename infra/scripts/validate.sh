#!/usr/bin/env bash
set -euo pipefail

readonly REQUIRED_TERRAFORM_VERSION="${REQUIRED_TERRAFORM_VERSION:-1.10.5}"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if ! command -v terraform >/dev/null 2>&1; then
  echo "terraform is required but was not found in PATH." >&2
  echo "Install Terraform ${REQUIRED_TERRAFORM_VERSION} or run the GitHub Actions infra-validate job." >&2
  exit 127
fi

installed_version="$(terraform version | awk 'NR==1 { gsub(/^v/, "", $2); print $2 }')"
if [[ "${installed_version}" != "${REQUIRED_TERRAFORM_VERSION}" ]]; then
  echo "Terraform version mismatch: expected ${REQUIRED_TERRAFORM_VERSION}, got ${installed_version}." >&2
  echo "Use Terraform ${REQUIRED_TERRAFORM_VERSION} for reproducible validate results." >&2
  exit 1
fi

terraform -chdir="${INFRA_DIR}" fmt -check -recursive
terraform -chdir="${INFRA_DIR}" init -backend=false -input=false
terraform -chdir="${INFRA_DIR}" validate
