variable "name_prefix" {
  type = string
}

variable "tool_names" {
  description = "Short names (without prefix) of the tool Lambdas to create, e.g. [\"quant-tools\", \"qual-tools\"]. Must match modules/iam's var.lambda_tool_names exactly - see that module's gateway_role.tf for why."
  type        = list(string)
  default     = ["quant-tools", "qual-tools"]
}

variable "lambda_execution_role_arn" {
  type = string
}

variable "dynamodb_table_name" {
  type = string
}

variable "opensearch_collection_endpoint" {
  type = string
}

variable "memory_size" {
  type    = number
  default = 256
}

variable "timeout_seconds" {
  type    = number
  default = 30
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "tags" {
  type    = map(string)
  default = {}
}
