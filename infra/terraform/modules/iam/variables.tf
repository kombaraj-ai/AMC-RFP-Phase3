variable "name_prefix" {
  description = "Naming prefix, e.g. \"amc-dev\"."
  type        = string
}

variable "aws_region" {
  type = string
}

variable "account_id" {
  type = string
}

variable "dynamodb_table_arn" {
  description = "ARN of the quant-metrics DynamoDB table."
  type        = string
}

variable "opensearch_collection_arn" {
  description = "ARN of the OpenSearch Serverless collection."
  type        = string
}

variable "kb_docs_bucket_arn" {
  description = "ARN of the S3 bucket holding Knowledge Base source documents."
  type        = string
}

variable "ecr_repository_arn" {
  description = "ARN of the ECR repository the runtime pulls its container image from."
  type        = string
}

variable "bedrock_model_arns" {
  description = "ARNs (or wildcarded foundation-model ARNs) the runtime/KB are allowed to invoke, e.g. Claude + Titan Embeddings."
  type        = list(string)
}

variable "lambda_tool_names" {
  description = "Short names (without prefix) of the Lambda tool functions the Gateway is allowed to invoke, e.g. [\"quant-tools\", \"qual-tools\"]. Must match modules/lambda-tools' var.tool_names exactly - see gateway_role.tf for why this is a naming convention, not a module output reference."
  type        = list(string)
}

variable "additional_data_access_principals" {
  description = <<-EOT
    Extra IAM principal ARNs (e.g. the human/CI role running `terraform apply`)
    to grant OpenSearch Serverless data-plane access. AOSS access is gated by
    its own data-access policy, not just IAM permissions - without this, the
    applier can create the collection but fail to create the vector index
    inside it.
  EOT
  type        = list(string)
  default     = []
}

variable "tags" {
  type    = map(string)
  default = {}
}
