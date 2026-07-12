output "collection_id" {
  value = var.enabled ? aws_opensearchserverless_collection.kb_vectors[0].id : ""
}

output "collection_arn" {
  value = var.enabled ? aws_opensearchserverless_collection.kb_vectors[0].arn : ""
}

output "collection_name" {
  value = local.collection_name
}

output "collection_endpoint" {
  description = "AOSS data-plane endpoint - feed this to the opensearch provider (modules/opensearch-index) to create the vector index in the documented second apply pass. Empty string when enabled = false (vector_store_backend = \"s3_vectors\")."
  value       = var.enabled ? aws_opensearchserverless_collection.kb_vectors[0].collection_endpoint : ""
}
