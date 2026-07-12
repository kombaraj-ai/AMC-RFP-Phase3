variable "name_prefix" {
  type = string
}

variable "enabled" {
  description = "Whether to actually create the collection and its policies. false when the dev-only vector_store_backend = \"s3_vectors\" is selected - kept as a module-internal count (not count on this module's own call site) so every consumer of this module's outputs (the opensearch provider block, root outputs.tf, modules/lambda-tools) can keep referencing them as plain singleton-module attributes, never a [0]-indexed one."
  type        = bool
  default     = true
}

variable "use_cmk" {
  description = "Encrypt the collection with a customer-managed KMS key instead of an AWS-owned key. Recommended for prod."
  type        = bool
  default     = false
}

variable "kms_key_arn" {
  description = "ARN of the CMK to use when use_cmk is true. Required in that case."
  type        = string
  default     = null
}

variable "standby_replicas" {
  description = "\"ENABLED\" (Recommended for staging/prod - multi-AZ standby, higher availability, roughly double cost) or \"DISABLED\" (single-AZ, cheaper - fine for dev)."
  type        = string
  default     = "DISABLED"

  validation {
    condition     = contains(["ENABLED", "DISABLED"], var.standby_replicas)
    error_message = "standby_replicas must be ENABLED or DISABLED."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}
