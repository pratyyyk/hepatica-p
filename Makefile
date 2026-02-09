.PHONY: preflight staging-plan staging-apply release-pack

preflight:
	./scripts/release_preflight.sh

staging-plan:
	./scripts/staging_deploy.sh --plan

staging-apply:
	./scripts/staging_deploy.sh --apply

release-pack:
	./scripts/release_dry_run_pack.sh
