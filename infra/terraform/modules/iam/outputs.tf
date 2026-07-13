output "runtime_role_arn" {
  value = aws_iam_role.runtime.arn
}

output "runtime_role_name" {
  value = aws_iam_role.runtime.name
}

output "gateway_role_arn" {
  value = aws_iam_role.gateway.arn
}

output "lambda_execution_role_arn" {
  value = aws_iam_role.lambda_execution.arn
}

output "knowledge_base_role_arn" {
  value = aws_iam_role.knowledge_base.arn
}

output "kb_ingestion_sync_role_arn" {
  value = aws_iam_role.kb_ingestion_sync.arn
}

output "data_access_principal_arns" {
  description = "Principals to grant OpenSearch Serverless data-plane access: the runtime, lambda, and KB roles, plus any human/CI principals passed in."
  value = concat(
    [
      aws_iam_role.runtime.arn,
      aws_iam_role.lambda_execution.arn,
      aws_iam_role.knowledge_base.arn,
    ],
    var.additional_data_access_principals,
  )
}
