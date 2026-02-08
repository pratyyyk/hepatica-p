variable "project_name" {
  type    = string
  default = "hepatica"
}

variable "environment" {
  type    = string
  default = "staging"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "db_name" {
  type    = string
  default = "hepatica"
}

variable "db_username" {
  type    = string
  default = "hepatica_admin"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "enable_sagemaker" {
  type    = bool
  default = false
}

variable "sagemaker_image_uri" {
  type    = string
  default = ""
}

variable "oauth_callback_urls" {
  type    = list(string)
  default = ["http://localhost:8000/api/v1/auth/callback"]
}

variable "oauth_logout_urls" {
  type    = list(string)
  default = ["http://localhost:3000"]
}

variable "cognito_domain_prefix" {
  type    = string
  default = ""
}

variable "frontend_redirect_uri" {
  type    = string
  default = "http://localhost:3000"
}

variable "cors_allowed_origins" {
  type    = list(string)
  default = ["http://localhost:3000"]
}

variable "session_encryption_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "enable_app_hosting" {
  type    = bool
  default = false
}

variable "backend_image_uri" {
  type    = string
  default = ""
}

variable "frontend_image_uri" {
  type    = string
  default = ""
}

variable "backend_public_base_url" {
  type    = string
  default = "http://localhost:8000"
}

variable "backend_service_cpu" {
  type    = string
  default = "1024"
}

variable "backend_service_memory" {
  type    = string
  default = "2048"
}

variable "frontend_service_cpu" {
  type    = string
  default = "1024"
}

variable "frontend_service_memory" {
  type    = string
  default = "2048"
}
