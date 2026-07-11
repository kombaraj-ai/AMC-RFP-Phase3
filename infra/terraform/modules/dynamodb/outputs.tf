output "table_name" {
  value = aws_dynamodb_table.quant_metrics.name
}

output "table_arn" {
  value = aws_dynamodb_table.quant_metrics.arn
}
