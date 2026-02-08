output "scan_bucket" {
  value = aws_s3_bucket.scan_bucket.id
}

output "report_bucket" {
  value = aws_s3_bucket.report_bucket.id
}

output "model_bucket" {
  value = aws_s3_bucket.model_bucket.id
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.doctor_pool.id
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.doctor_client.id
}

output "db_endpoint" {
  value = aws_db_instance.postgres.address
}

output "db_secret_arn" {
  value = aws_secretsmanager_secret.db_connection.arn
}

output "sagemaker_endpoint_name" {
  value = var.enable_sagemaker ? aws_sagemaker_endpoint.fibrosis[0].name : null
}
