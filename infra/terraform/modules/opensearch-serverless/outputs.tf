output "collection_id" {
  value = aws_opensearchserverless_collection.kb_vectors.id
}

output "collection_arn" {
  value = aws_opensearchserverless_collection.kb_vectors.arn
}

output "collection_name" {
  value = local.collection_name
}

output "collection_endpoint" {
  description = "AOSS data-plane endpoint - feed this to the opensearch provider (modules/opensearch-index) to create the vector index in the documented second apply pass."
  value       = aws_opensearchserverless_collection.kb_vectors.collection_endpoint
}
