variable "name_prefix" {
  type = string
}

variable "point_in_time_recovery_enabled" {
  description = "Continuous backups for the last 35 days. Recommended on for staging/prod, optional in dev to save a small amount of cost."
  type        = bool
  default     = true
}

variable "use_cmk" {
  description = "Encrypt with a customer-managed KMS key instead of the AWS-owned default. Recommended for prod."
  type        = bool
  default     = false
}

variable "deletion_protection_enabled" {
  description = "Blocks accidental `terraform destroy`/console deletion of the table. Recommended on for staging/prod."
  type        = bool
  default     = false
}

variable "tags" {
  type    = map(string)
  default = {}
}
