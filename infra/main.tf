resource "random_id" "suffix" {
  byte_length = 3
}

locals {
  prefix = "${var.project_name}-${var.environment}-${random_id.suffix.hex}"
  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_s3_bucket" "scan_bucket" {
  bucket = "${local.prefix}-scans"
  tags   = local.tags
}

resource "aws_s3_bucket_versioning" "scan_bucket" {
  bucket = aws_s3_bucket.scan_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "scan_bucket" {
  bucket = aws_s3_bucket.scan_bucket.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket" "report_bucket" {
  bucket = "${local.prefix}-reports"
  tags   = local.tags
}

resource "aws_s3_bucket_versioning" "report_bucket" {
  bucket = aws_s3_bucket.report_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "report_bucket" {
  bucket = aws_s3_bucket.report_bucket.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket" "model_bucket" {
  bucket = "${local.prefix}-models"
  tags   = local.tags
}

resource "aws_s3_bucket_versioning" "model_bucket" {
  bucket = aws_s3_bucket.model_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_cognito_user_pool" "doctor_pool" {
  name = "${local.prefix}-doctor-pool"

  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]

  password_policy {
    minimum_length    = 10
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }

  tags = local.tags
}

resource "aws_cognito_user_pool_client" "doctor_client" {
  name         = "${local.prefix}-doctor-client"
  user_pool_id = aws_cognito_user_pool.doctor_pool.id

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  prevent_user_existence_errors = "ENABLED"
  generate_secret               = false
}

resource "aws_cognito_user_group" "doctor_group" {
  user_pool_id = aws_cognito_user_pool.doctor_pool.id
  name         = "DOCTOR"
  description  = "Doctor role for Hepatica"
}

resource "aws_security_group" "rds" {
  name        = "${local.prefix}-rds-sg"
  description = "RDS security group"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

resource "aws_db_subnet_group" "postgres" {
  name       = "${local.prefix}-db-subnet"
  subnet_ids = var.private_subnet_ids
  tags       = local.tags
}

resource "aws_db_instance" "postgres" {
  identifier              = "${replace(local.prefix, "-", "")}-pg"
  allocated_storage       = 20
  max_allocated_storage   = 100
  engine                  = "postgres"
  engine_version          = "14.17"
  instance_class          = var.db_instance_class
  db_name                 = var.db_name
  username                = var.db_username
  password                = var.db_password
  publicly_accessible     = false
  db_subnet_group_name    = aws_db_subnet_group.postgres.name
  vpc_security_group_ids  = [aws_security_group.rds.id]
  backup_retention_period = 7
  storage_encrypted       = true
  skip_final_snapshot     = true
  deletion_protection     = false
  apply_immediately       = true
  tags                    = local.tags
}

resource "aws_secretsmanager_secret" "db_connection" {
  name = "${local.prefix}/database"
  tags = local.tags
}

resource "aws_secretsmanager_secret_version" "db_connection" {
  secret_id = aws_secretsmanager_secret.db_connection.id
  secret_string = jsonencode({
    username = var.db_username
    password = var.db_password
    host     = aws_db_instance.postgres.address
    port     = aws_db_instance.postgres.port
    dbname   = var.db_name
  })
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/${var.project_name}/${var.environment}/api"
  retention_in_days = 30
  tags              = local.tags
}

resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${local.prefix}-rds-high-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "High CPU on RDS"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.postgres.id
  }

  tags = local.tags
}

resource "aws_cloudwatch_dashboard" "ops" {
  dashboard_name = "${local.prefix}-ops"
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "RDS CPU"
          region  = var.aws_region
          metrics = [["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", aws_db_instance.postgres.id]]
          stat    = "Average"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "API Log Events"
          region  = var.aws_region
          metrics = [["AWS/Logs", "IncomingLogEvents", "LogGroupName", aws_cloudwatch_log_group.api.name]]
          stat    = "Sum"
          period  = 300
        }
      }
    ]
  })
}

resource "aws_iam_role" "sagemaker_execution" {
  name = "${local.prefix}-sagemaker-exec"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "sagemaker.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "sagemaker_full" {
  role       = aws_iam_role.sagemaker_execution.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess"
}

resource "aws_sagemaker_model" "fibrosis" {
  count              = var.enable_sagemaker ? 1 : 0
  name               = "${local.prefix}-fibrosis-model"
  execution_role_arn = aws_iam_role.sagemaker_execution.arn

  primary_container {
    image          = var.sagemaker_image_uri
    model_data_url = "s3://${aws_s3_bucket.model_bucket.id}/fibrosis/v1/model.tar.gz"
  }

  tags = local.tags
}

resource "aws_sagemaker_endpoint_configuration" "fibrosis" {
  count = var.enable_sagemaker ? 1 : 0
  name  = "${local.prefix}-fibrosis-endpoint-config"

  production_variants {
    variant_name           = "all-traffic"
    model_name             = aws_sagemaker_model.fibrosis[0].name
    initial_instance_count = 1
    instance_type          = "ml.m5.large"
  }

  tags = local.tags
}

resource "aws_sagemaker_endpoint" "fibrosis" {
  count                = var.enable_sagemaker ? 1 : 0
  name                 = "${local.prefix}-fibrosis-endpoint"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.fibrosis[0].name
  tags                 = local.tags
}
