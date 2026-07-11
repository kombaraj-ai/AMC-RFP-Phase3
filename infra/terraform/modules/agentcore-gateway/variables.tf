variable "name_prefix" {
  type = string
}

variable "gateway_role_arn" {
  type = string
}

variable "kms_key_arn" {
  description = "Optional CMK for gateway data encryption. Null uses AWS-managed encryption."
  type        = string
  default     = null
}

variable "lambda_tools" {
  description = <<-EOT
    Map of tool short-name -> { lambda_arn, description }. One
    gateway_target per entry, each exposing a single generic
    `invoke(query: string) -> result: string` tool - a placeholder shape
    matching the stub Lambdas in modules/lambda-tools; replace with real
    per-tool input/output schemas in the app-code follow-on task.
  EOT
  type = map(object({
    lambda_arn  = string
    description = string
  }))
}

variable "tags" {
  type    = map(string)
  default = {}
}
