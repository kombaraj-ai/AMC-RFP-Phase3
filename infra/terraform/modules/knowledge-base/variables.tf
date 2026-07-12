variable "name_prefix" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "knowledge_base_role_arn" {
  type = string
}

variable "docs_bucket_arn" {
  type = string
}

variable "vector_store_backend" {
  description = "Which storage_configuration block to render: \"opensearch\" or \"s3_vectors\". Must match environments/*/variables.tf's var.vector_store_backend exactly."
  type        = string

  validation {
    condition     = contains(["opensearch", "s3_vectors"], var.vector_store_backend)
    error_message = "vector_store_backend must be \"opensearch\" or \"s3_vectors\"."
  }
}

variable "opensearch_collection_arn" {
  type    = string
  default = ""
}

variable "vector_index_name" {
  description = "Must match modules/opensearch-index's var.index_name exactly - the index is created out-of-band by that module in a second apply pass, this resource only references it by name. Only used when vector_store_backend = \"opensearch\"."
  type        = string
  default     = "kb-default-index"
}

variable "s3_vectors_bucket_arn" {
  description = "modules/s3-vectors' vector_bucket_arn output. Only used when vector_store_backend = \"s3_vectors\"."
  type        = string
  default     = ""
}

variable "s3_vectors_index_arn" {
  description = "modules/s3-vectors' index_arn output. Only used when vector_store_backend = \"s3_vectors\"."
  type        = string
  default     = ""
}

variable "s3_vectors_index_name" {
  description = "modules/s3-vectors' index_name output. Only used when vector_store_backend = \"s3_vectors\"."
  type        = string
  default     = ""
}

variable "vector_field" {
  type    = string
  default = "bedrock-knowledge-base-default-vector"
}

variable "text_field" {
  type    = string
  default = "AMAZON_BEDROCK_TEXT_CHUNK"
}

variable "metadata_field" {
  type    = string
  default = "AMAZON_BEDROCK_METADATA"
}

variable "embedding_model" {
  description = "Choice of Bedrock embedding model. \"titan-v2\" (Recommended - 1024-dim default, cheapest, no extra access request) or \"cohere-multilingual\" (better non-English recall, needs separate model access approval)."
  type        = string
  default     = "titan-v2"

  validation {
    condition     = contains(["titan-v2", "cohere-multilingual"], var.embedding_model)
    error_message = "embedding_model must be \"titan-v2\" or \"cohere-multilingual\"."
  }
}

variable "chunking_max_tokens" {
  type    = number
  default = 512
}

variable "chunking_overlap_percentage" {
  type    = number
  default = 20
}

variable "data_deletion_policy" {
  description = "\"RETAIN\" (Recommended for prod - keeps ingested vectors on data-source deletion) or \"DELETE\"."
  type        = string
  default     = "RETAIN"
}

variable "tags" {
  type    = map(string)
  default = {}
}
