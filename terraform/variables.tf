variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Project name prefix used for all resource names"
  type        = string
  default     = "multi-agent-bedrock"
}

variable "environment" {
  description = "Deployment environment (dev / staging / prod)"
  type        = string
  default     = "dev"
}

variable "docs_bucket_suffix" {
  description = "Suffix appended to the docs S3 bucket name (use account ID for global uniqueness)"
  type        = string
  default     = ""
}

variable "images_bucket_suffix" {
  description = "Suffix appended to the images S3 bucket name"
  type        = string
  default     = ""
}

variable "lambda_runtime" {
  description = "Lambda runtime for all functions"
  type        = string
  default     = "python3.12"
}

variable "lambda_timeout" {
  description = "Default Lambda timeout in seconds"
  type        = number
  default     = 300
}

variable "lambda_memory_mb" {
  description = "Default Lambda memory in MB"
  type        = number
  default     = 256
}

variable "image_presigned_url_expiry" {
  description = "Expiry seconds for generated image presigned URLs"
  type        = number
  default     = 3600
}
