# infra (Terraform)

Terraform configuration for a legacy AWS-backed staging environment.

Why it exists:
- supports cloud deployments when needed
- keeps infrastructure changes versioned and reviewable

Why it is optional:
- the prototype is local-first and can run end-to-end without AWS.

Common commands:

```bash
cd infra
./scripts/validate.sh
```

Top-level helpers:
- `make staging-plan`
- `make staging-apply`

