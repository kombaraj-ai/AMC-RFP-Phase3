variable "name_prefix" {
  type = string
}

variable "account_id" {
  type = string
}

variable "use_cmk" {
  description = "Encrypt with a customer-managed KMS key instead of SSE-S3. Recommended for prod."
  type        = bool
  default     = false
}

variable "noncurrent_version_expiration_days" {
  type    = number
  default = 90
}

variable "tags" {
  type    = map(string)
  default = {}
}
