variable "collection_name" {
  type = string
}

variable "enabled" {
  description = "Whether to actually create the access policy. false when the dev-only vector_store_backend = \"s3_vectors\" is selected - kept as a module-internal count, mirroring modules/opensearch-serverless's var.enabled, so this module's call site never needs count/[0]-indexing either."
  type        = bool
  default     = true
}

variable "principal_arns" {
  description = "IAM principal ARNs granted full data-plane access (index create/read/write) to the collection - modules/iam's data_access_principal_arns output."
  type        = list(string)
}

variable "tags" {
  type    = map(string)
  default = {}
}
