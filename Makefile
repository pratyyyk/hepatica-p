.PHONY: preflight staging-plan staging-apply

preflight:
	./scripts/release_preflight.sh

staging-plan:
	./scripts/staging_deploy.sh --plan

staging-apply:
	./scripts/staging_deploy.sh --apply
