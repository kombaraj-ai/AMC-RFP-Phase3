output "queue_arn" {
  value = aws_sqs_queue.events.arn
}

output "dlq_arn" {
  value = aws_sqs_queue.dlq.arn
}

output "dlq_name" {
  value = aws_sqs_queue.dlq.name
}

output "lambda_function_name" {
  value = aws_lambda_function.ingestion_sync.function_name
}
