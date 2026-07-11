variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "amc-orchestrator"
}

variable "environment" {
  type    = string
  default = "prod"

  validation {
    condition     = var.environment == "prod"
    error_message = "This root module is prod-only; environments/dev and environments/staging are separate root modules."
  }
}

# --- Phased-apply gates (see README.md) -------------------------------
variable "enable_knowledge_base" {
  description = "Set true only after a first apply has created the OpenSearch collection. Creates the vector index (via the opensearch provider) and the Bedrock Knowledge Base together, since the KB cannot be created without the index existing first."
  type        = bool
  default     = false
}

variable "enable_agent_runtime" {
  description = "Set true only after a real image has been pushed to the ECR repo this stack creates. See var.container_image_uri."
  type        = bool
  default     = false
}

variable "container_image_uri" {
  description = "Required only when enable_agent_runtime = true. Full ECR image URI including tag."
  type        = string
  default     = ""
}

# --- Cost/HA knobs -------------------------------------------------------
variable "use_cmk" {
  description = "Customer-managed KMS keys instead of AWS-managed encryption across S3/DynamoDB/OpenSearch/Memory. Always on in prod - an AMC's client RFP data warrants a full customer-controlled audit trail."
  type        = bool
  default     = true
}

variable "opensearch_standby_replicas" {
  type    = string
  default = "ENABLED"
}

variable "dynamodb_point_in_time_recovery" {
  type    = bool
  default = true
}

variable "dynamodb_deletion_protection" {
  type    = bool
  default = true
}

variable "log_retention_days" {
  type    = number
  default = 365
}

variable "memory_event_expiry_days" {
  type    = number
  default = 90
}

variable "ecr_untagged_image_expiry_days" {
  type    = number
  default = 30
}

variable "ecr_max_tagged_images" {
  type    = number
  default = 30
}

variable "alarm_email" {
  type    = string
  default = ""
}

# --- Model choices ---------------------------------------------------------
variable "bedrock_model_id" {
  description = "Foundation model the agent runtime invokes - matches Settings.bedrock_model_id in the app's config/settings.py."
  type        = string
  default     = "anthropic.claude-3-5-sonnet-20241022-v2:0"
}

variable "embedding_model" {
  type    = string
  default = "titan-v2"
}

variable "runtime_protocol" {
  type    = string
  default = "HTTP"
}

variable "lambda_tool_names" {
  type    = list(string)
  default = ["quant-tools", "qual-tools"]
}

variable "additional_data_access_principals" {
  description = "Extra IAM principal ARNs (e.g. the human/CI role applying this stack) to grant OpenSearch Serverless data-plane access, needed for pass 2's index creation to succeed."
  type        = list(string)
  default     = []
}
