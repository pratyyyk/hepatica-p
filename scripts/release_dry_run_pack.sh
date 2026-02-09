#!/usr/bin/env bash
set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"

OUT_BASE="${ROOT_DIR}/artifacts/release"
RUN_SMOKE="true"
RUN_PREFLIGHT="false"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/release_dry_run_pack.sh [--out-base DIR] [--skip-smoke] [--run-preflight]

Defaults:
  out-base      artifacts/release
  run-smoke     true
  run-preflight false
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out-base)
      OUT_BASE="$2"
      shift 2
      ;;
    --skip-smoke)
      RUN_SMOKE="false"
      shift
      ;;
    --run-preflight)
      RUN_PREFLIGHT="true"
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

BUNDLE_DIR="${OUT_BASE}/${TIMESTAMP}"
mkdir -p "${BUNDLE_DIR}"

BRANCH="$(git -C "${ROOT_DIR}" branch --show-current)"
SHA="$(git -C "${ROOT_DIR}" rev-parse --short HEAD)"

cat > "${BUNDLE_DIR}/01_environment.md" <<EOF
# Release Dry-Run Environment

- generated_at_utc: \`${TIMESTAMP}\`
- branch: \`${BRANCH}\`
- commit: \`${SHA}\`
- working_dir: \`${ROOT_DIR}\`
EOF

cat > "${BUNDLE_DIR}/02_commands.md" <<'EOF'
# Release Commands

## Local preflight

```bash
cd /Users/praty/hepatica-p
make preflight
```

## UAT evidence

```bash
cd /Users/praty/hepatica-p/backend
make smoke-evidence
```

## Staging deploy (when AWS is available)

```bash
cd /Users/praty/hepatica-p
make staging-plan
make staging-apply
```
EOF

cat > "${BUNDLE_DIR}/03_expected_outputs.md" <<'EOF'
# Expected Outputs

1. `make preflight` ends with `Release preflight passed.`
2. `make smoke-evidence` produces:
   - `backend/artifacts/uat/uat_evidence.json`
   - `backend/artifacts/uat/uat_evidence.md`
3. Staging backend responds `200` on `/healthz`.
4. Latest `ci` workflow run is `success`.
EOF

cat > "${BUNDLE_DIR}/04_go_no_go.md" <<'EOF'
# Go / No-Go

- [ ] Backend tests pass
- [ ] Backend smoke flow passes
- [ ] Frontend lint/audit/build pass
- [ ] Infra validate passes
- [ ] UAT evidence JSON+MD generated
- [ ] Latest CI run is green
- [ ] Staging deploy healthy (if staging path is in scope)

Decision:
- [ ] GO
- [ ] NO-GO

Notes:

EOF

cat > "${BUNDLE_DIR}/05_rollback.md" <<'EOF'
# Rollback Playbook (App + Model)

## App rollback

1. Re-deploy previous known-good git SHA.
2. Re-run smoke flow and `/healthz`.

## Model rollback

1. Activate previous model version:

```bash
cd /Users/praty/hepatica-p/backend
python3 scripts/model_registry.py activate --name clinical-stage1-gbdt --version <prev-version>
python3 scripts/model_registry.py activate --name fibrosis-efficientnet-b3 --version <prev-version>
```

2. Verify:

```bash
curl -s http://localhost:8000/api/v1/models/status
```
EOF

if [[ "${RUN_SMOKE}" == "true" ]]; then
  (
    cd "${ROOT_DIR}/backend"
    python3 scripts/smoke_evidence.py \
      --out-json "${BUNDLE_DIR}/uat_evidence.json" \
      --out-md "${BUNDLE_DIR}/uat_evidence.md"
  )
fi

if [[ "${RUN_PREFLIGHT}" == "true" ]]; then
  (
    cd "${ROOT_DIR}"
    make preflight | tee "${BUNDLE_DIR}/preflight.log"
  )
fi

echo "Release dry-run pack generated: ${BUNDLE_DIR}"
