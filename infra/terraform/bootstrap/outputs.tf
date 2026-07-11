output "state_bucket_name" {
  description = "S3 bucket name to reference from every environment's backend.tf."
  value       = aws_s3_bucket.state.id
}

output "state_bucket_arn" {
  value = aws_s3_bucket.state.arn
}

output "state_bucket_region" {
  value = var.aws_region
}

output "kms_key_arn" {
  description = "ARN of the state-encryption CMK, if SSE-KMS was chosen (null otherwise)."
  value       = local.use_kms ? aws_kms_key.state[0].arn : null
}
