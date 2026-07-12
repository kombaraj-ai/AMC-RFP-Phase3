variable "name_prefix" {
  type = string
}

variable "account_id" {
  type = string
}

variable "index_name" {
  description = "Vector index name. Must match modules/knowledge-base's var.s3_vectors_index_name exactly."
  type        = string
  default     = "kb-default-index"
}

variable "embedding_dimension" {
  description = "Must match the embedding model's output dimension - 1024 for Titan Text Embeddings V2 at its default dimension."
  type        = number
  default     = 1024
}

variable "data_type" {
  description = <<-EOT
    S3 Vectors index element data type. "float32" per AWS's reference examples -
    not independently verified against authoritative AWS docs as of this module's
    creation; confirm before relying on this in a cost-sensitive or
    production-adjacent context (see docs/architecture.md's Phase 02 section).
  EOT
  type        = string
  default     = "float32"
}

variable "distance_metric" {
  description = <<-EOT
    S3 Vectors similarity metric. "cosine" per AWS's reference examples - note
    this differs from modules/opensearch-index's "l2" (Euclidean), a different
    metric family; not independently verified as the correct/recommended choice
    for a Titan V2 embedding-backed Knowledge Base. Confirm before relying on
    this in a cost-sensitive or production-adjacent context.
  EOT
  type        = string
  default     = "cosine"

  validation {
    condition     = contains(["cosine", "euclidean"], var.distance_metric)
    error_message = "distance_metric must be \"cosine\" or \"euclidean\"."
  }
}

variable "non_filterable_metadata_keys" {
  description = "Metadata keys excluded from filtering (S3 Vectors has filterable-metadata size limits, unlike OpenSearch). Empty by default - add here if Bedrock's chunk-text metadata field needs to be excluded once confirmed against AWS docs."
  type        = set(string)
  default     = []
}

variable "use_cmk" {
  description = "Encrypt the vector bucket with a customer-managed KMS key instead of an AWS-managed key."
  type        = bool
  default     = false
}

variable "tags" {
  type    = map(string)
  default = {}
}
