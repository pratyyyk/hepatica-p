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
