variable "name_prefix" {
  type = string
}

variable "event_expiry_days" {
  description = "How long AgentCore retains raw conversation events (7-365). Shorter in dev to bound cost, longer in prod for audit/compliance needs typical of an AMC's client-facing RFP responses."
  type        = number
  default     = 30

  validation {
    condition     = var.event_expiry_days >= 7 && var.event_expiry_days <= 365
    error_message = "event_expiry_days must be between 7 and 365."
  }
}

variable "use_cmk" {
  description = "Encrypt memory records with a customer-managed KMS key instead of AWS-managed encryption. Recommended for prod."
  type        = bool
  default     = false
}

variable "kms_key_arn" {
  type    = string
  default = null
}

variable "tags" {
  type    = map(string)
  default = {}
}
