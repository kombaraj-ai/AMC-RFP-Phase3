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
  default = "dev"

  validation {
    condition     = var.environment == "dev"
    error_message = "This root module is dev-only; environments/staging and environments/prod are separate root modules."
  }
}

# --- Phased-apply gates (see README.md) -------------------------------
variable "enable_knowledge_base" {
  description = "Set true only after a first apply has created the OpenSearch collection. Creates the vector index (via the opensearch provider) and the Bedrock Knowledge Base together, since the KB cannot be created without the index existing first."
  type        = bool
  default     = false
}

variable "vector_store_backend" {
  description = "Vector store backing the Bedrock Knowledge Base: \"opensearch\" (Amazon OpenSearch Serverless) or \"s3_vectors\" (Amazon S3 Vectors - cheapest, dev-only). \"s3_vectors\" creates zero OpenSearch resources, including the collection itself, for full cost savings (see docs/architecture.md's \"Dev-only vector store choice\" section)."
  type        = string
  default     = "opensearch"

  validation {
    condition     = contains(["opensearch", "s3_vectors"], var.vector_store_backend)
    error_message = "vector_store_backend must be \"opensearch\" or \"s3_vectors\"."
  }
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
  description = "Customer-managed KMS keys instead of AWS-managed encryption across S3/DynamoDB/OpenSearch/Memory. Off by default in dev to save cost."
  type        = bool
  default     = false
}

variable "opensearch_standby_replicas" {
  type    = string
  default = "DISABLED"
}

variable "dynamodb_point_in_time_recovery" {
  type    = bool
  default = false
}

variable "dynamodb_deletion_protection" {
  type    = bool
  default = false
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "memory_event_expiry_days" {
  type    = number
  default = 14
}

variable "ecr_untagged_image_expiry_days" {
  type    = number
  default = 7
}

variable "ecr_max_tagged_images" {
  type    = number
  default = 10
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
