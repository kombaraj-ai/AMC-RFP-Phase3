variable "collection_name" {
  type = string
}

variable "principal_arns" {
  description = "IAM principal ARNs granted full data-plane access (index create/read/write) to the collection - modules/iam's data_access_principal_arns output."
  type        = list(string)
}

variable "tags" {
  type    = map(string)
  default = {}
}
