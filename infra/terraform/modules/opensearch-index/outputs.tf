output "index_name" {
  value = opensearch_index.kb_vector_index.name
}

output "vector_field" {
  value = var.vector_field
}

output "text_field" {
  value = var.text_field
}

output "metadata_field" {
  value = var.metadata_field
}
