# AWS Infrastructure (Terraform)

## Resources provisioned

- Cognito user pool + client + `DOCTOR` group
- RDS PostgreSQL + subnet group + security group
- S3 buckets for scans, reports, and model artifacts
- Secrets Manager secret with DB connection fields
- CloudWatch log group, dashboard, and RDS CPU alarm
- Optional SageMaker model + endpoint (`enable_sagemaker=true`)

## Usage

```bash
cd /Users/praty/hepatica-p/infra
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
```

## Notes

- `enable_sagemaker` defaults to `false` to avoid accidental endpoint cost.
- Restrict SG ingress CIDRs for production.
- Add KMS CMKs and stricter IAM policies before production launch.
