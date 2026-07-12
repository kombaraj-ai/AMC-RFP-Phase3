output "vector_bucket_name" {
  value = aws_s3vectors_vector_bucket.kb_vectors.vector_bucket_name
}

output "vector_bucket_arn" {
  value = aws_s3vectors_vector_bucket.kb_vectors.vector_bucket_arn
}

output "index_name" {
  value = aws_s3vectors_index.kb_vector_index.index_name
}

output "index_arn" {
  value = aws_s3vectors_index.kb_vector_index.index_arn
}
