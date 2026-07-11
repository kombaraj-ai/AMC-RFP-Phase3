variable "aws_region" {
  description = "AWS region the state bucket lives in."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project name, used as a naming prefix for the state bucket."
  type        = string
  default     = "amc-orchestrator"
}

variable "state_bucket_encryption" {
  description = "Server-side encryption for the state bucket: \"SSE-S3\" (AWS-managed, free) or \"SSE-KMS\" (customer-managed key, extra cost, tighter audit trail)."
  type        = string
  default     = "SSE-S3"

  validation {
    condition     = contains(["SSE-S3", "SSE-KMS"], var.state_bucket_encryption)
    error_message = "state_bucket_encryption must be either \"SSE-S3\" or \"SSE-KMS\"."
  }
}

variable "noncurrent_version_expiration_days" {
  description = "Days to retain noncurrent state file versions before expiring them (versioning stays on regardless; this only bounds storage growth)."
  type        = number
  default     = 90
}

variable "tags" {
  description = "Common tags applied to all bootstrap resources."
  type        = map(string)
  default     = {}
}
