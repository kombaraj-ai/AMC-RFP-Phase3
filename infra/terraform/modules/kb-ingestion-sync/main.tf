# S3 docs bucket -> SQS (batches events, debounces concurrent Bedrock
# ingestion jobs since only one can run per data source at a time) -> Lambda
# (start_ingestion_job) -> DLQ on genuine failure. See
# modules/iam/kb_ingestion_sync_role.tf for the Lambda's execution role and
# why bedrock:StartIngestionJob is wildcarded there instead of scoped to this
# module's real knowledge_base_id (avoids an iam<->knowledge_base module
# cycle - see that file's comment).

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name_prefix}-kb-ingestion-dlq"
  message_retention_seconds = var.sqs_message_retention_seconds
  tags                      = var.tags
}

resource "aws_sqs_queue" "events" {
  # Name is explicit (not auto-generated) because modules/iam's
  # kb_ingestion_sync_role.tf grants sqs:ReceiveMessage/DeleteMessage/
  # GetQueueAttributes to this exact ARN by naming convention, not a real
  # reference - the two must stay in sync if either changes.
  name = "${var.name_prefix}-kb-ingestion-events"

  # >= 6x the Lambda's timeout, per AWS's own SQS-Lambda guidance, so a
  # message can't become visible again mid-invocation.
  visibility_timeout_seconds = var.lambda_timeout_seconds * 6

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.dlq_max_receive_count
  })

  tags = var.tags
}

data "aws_iam_policy_document" "events_queue_policy" {
  statement {
    sid     = "AllowS3SendMessage"
    effect  = "Allow"
    actions = ["sqs:SendMessage"]
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
    resources = [aws_sqs_queue.events.arn]
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [var.docs_bucket_arn]
    }
  }
}

resource "aws_sqs_queue_policy" "events" {
  queue_url = aws_sqs_queue.events.id
  policy    = data.aws_iam_policy_document.events_queue_policy.json
}

resource "aws_s3_bucket_notification" "docs" {
  bucket = var.docs_bucket_id

  queue {
    queue_arn = aws_sqs_queue.events.arn
    events    = ["s3:ObjectCreated:*", "s3:ObjectRemoved:*"]
  }

  depends_on = [aws_sqs_queue_policy.events]
}

resource "aws_cloudwatch_log_group" "ingestion_sync" {
  name              = "/aws/lambda/${var.name_prefix}-kb-ingestion-sync"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

data "archive_file" "sync" {
  type        = "zip"
  source_dir  = "${path.module}/sync_src"
  output_path = "${path.module}/.build/sync.zip"
}

resource "aws_lambda_function" "ingestion_sync" {
  function_name = "${var.name_prefix}-kb-ingestion-sync"
  role          = var.ingestion_sync_role_arn
  handler       = "handler.handler"
  runtime       = "python3.13"
  memory_size   = var.lambda_memory_size
  timeout       = var.lambda_timeout_seconds

  filename         = data.archive_file.sync.output_path
  source_code_hash = data.archive_file.sync.output_base64sha256

  environment {
    variables = {
      KNOWLEDGE_BASE_ID = var.knowledge_base_id
      DATA_SOURCE_ID    = var.data_source_id
    }
  }

  tags = var.tags

  depends_on = [aws_cloudwatch_log_group.ingestion_sync]
}

resource "aws_lambda_event_source_mapping" "events" {
  event_source_arn = aws_sqs_queue.events.arn
  function_name    = aws_lambda_function.ingestion_sync.function_name
  batch_size       = var.batch_size

  maximum_batching_window_in_seconds = var.maximum_batching_window_seconds
}
