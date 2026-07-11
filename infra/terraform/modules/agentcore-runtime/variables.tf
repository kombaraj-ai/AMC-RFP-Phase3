variable "name_prefix" {
  type = string
}

variable "runtime_role_arn" {
  type = string
}

variable "container_image_uri" {
  description = <<-EOT
    Full ECR image URI including tag, e.g.
    "<account>.dkr.ecr.<region>.amazonaws.com/amc-dev-agent-runtime:v1".
    Deliberately has NO default: modules/ecr only creates the repository,
    it never builds/pushes an image. Push a real image (CI/CD or manual)
    before applying this module - see infra/terraform/README.md's
    "artifact bootstrap" section for the documented two-pass apply.
  EOT
  type        = string

  validation {
    condition     = length(trimspace(var.container_image_uri)) > 0
    error_message = "container_image_uri must be set to a real, already-pushed ECR image URI - see the variable description."
  }
}

variable "environment_variables" {
  description = "Env vars passed to the running container - table names, endpoints, etc. Never put secrets here directly; use Secrets Manager/SSM references resolved at container startup instead."
  type        = map(string)
  default     = {}
}

variable "protocol" {
  description = "Server protocol the runtime container speaks. \"HTTP\" (Recommended - matches the existing FastAPI layer most closely), \"MCP\", \"A2A\", or \"AGUI\"."
  type        = string
  default     = "HTTP"

  validation {
    condition     = contains(["HTTP", "MCP", "A2A", "AGUI"], var.protocol)
    error_message = "protocol must be one of HTTP, MCP, A2A, AGUI."
  }
}

variable "idle_session_timeout_seconds" {
  type    = number
  default = 900
}

variable "max_lifetime_seconds" {
  description = "Maximum lifetime of a single runtime instance in seconds, regardless of activity."
  type        = number
  default     = 28800
}

variable "tags" {
  type    = map(string)
  default = {}
}
