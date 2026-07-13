variable "name_prefix" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "docs_bucket_id" {
  description = "modules/s3-kb-docs' bucket_name output (the bucket id, not ARN - aws_s3_bucket_notification's bucket argument takes the id)."
  type        = string
}

variable "docs_bucket_arn" {
  type = string
}

variable "knowledge_base_id" {
  type = string
}

variable "data_source_id" {
  type = string
}

variable "ingestion_sync_role_arn" {
  description = "modules/iam's kb_ingestion_sync_role_arn output. That role's SQS statement is scoped by predictable name to \"$${name_prefix}-kb-ingestion-events\" - aws_sqs_queue.events' name below must match it exactly."
  type        = string
}

variable "batch_size" {
  description = "Max SQS messages per Lambda invocation."
  type        = number
  default     = 10
}

variable "maximum_batching_window_seconds" {
  description = "How long the event source mapping waits to accumulate a batch before invoking the Lambda - the primary debounce mechanism so many rapid S3 events collapse into one ingestion job, since Bedrock only allows one running ingestion job per data source at a time."
  type        = number
  default     = 300
}

variable "dlq_max_receive_count" {
  description = "Failed deliveries are redriven to the DLQ after this many receives."
  type        = number
  default     = 3
}

variable "sqs_message_retention_seconds" {
  type    = number
  default = 1209600 # 14 days
}

variable "lambda_timeout_seconds" {
  type    = number
  default = 120
}

variable "lambda_memory_size" {
  type    = number
  default = 256
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "tags" {
  type    = map(string)
  default = {}
}
