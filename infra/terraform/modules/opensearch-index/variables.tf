variable "index_name" {
  description = "Vector index name. Must match modules/knowledge-base's var.vector_index_name exactly."
  type        = string
  default     = "kb-default-index"
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

variable "embedding_dimension" {
  description = "Must match the embedding model's output dimension - 1024 for Titan Text Embeddings V2 at its default dimension."
  type        = number
  default     = 1024
}
