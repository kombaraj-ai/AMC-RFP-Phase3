# --- kb_ingestion_sync_role -------------------------------------------------
# Assumed by modules/kb-ingestion-sync's Lambda, which start_ingestion_jobs
# the Bedrock Knowledge Base whenever the docs bucket changes.

data "aws_iam_policy_document" "kb_ingestion_sync_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "kb_ingestion_sync" {
  name               = "${var.name_prefix}-kb-ingestion-sync-role"
  assume_role_policy = data.aws_iam_policy_document.kb_ingestion_sync_trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "kb_ingestion_sync_permissions" {
  statement {
    sid     = "BedrockStartIngestionJob"
    effect  = "Allow"
    actions = ["bedrock:StartIngestionJob"]
    # Wildcarded rather than scoped to one KB ARN: the real KB ARN doesn't
    # exist until Pass 2 (module.knowledge_base), but this role is created
    # in Pass 1 (this module) - scoping it precisely would recreate the same
    # iam<->knowledge_base cycle already solved once for OpenSearch's access
    # policy (see modules/opensearch-access-policy). Confirmed acceptable
    # trade-off with the user: this grants only the ability to *trigger*
    # ingestion jobs account-wide, not read/write KB content.
    resources = ["arn:aws:bedrock:${var.aws_region}:${var.account_id}:knowledge-base/*"]
  }

  statement {
    sid     = "SQSConsumeIngestionEvents"
    effect  = "Allow"
    actions = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    # Predictable ARN by naming convention, same precedent as
    # lambda_execution_role.tf's CloudWatchLogsOwnFunctions statement -
    # avoids needing the real queue ARN as a module input (which would
    # require this module to depend on modules/kb-ingestion-sync, which
    # itself depends on this module's role output).
    resources = ["arn:aws:sqs:${var.aws_region}:${var.account_id}:${var.name_prefix}-kb-ingestion-events"]
  }

  statement {
    sid     = "CloudWatchLogsOwnFunction"
    effect  = "Allow"
    actions = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:CreateLogGroup"]
    # Trailing ":*" required to cover log-stream sub-resources, not just the
    # log group itself - without it, CreateLogStream/PutLogEvents silently
    # fail (Lambda invocations still succeed; log delivery is best-effort
    # and doesn't block the invocation). Matches AWS's own
    # AWSLambdaBasicExecutionRole pattern
    # ("log-group:/aws/lambda/*:*"). Found via a real dev invocation: 6
    # successful (0-error) Lambda invocations produced zero CloudWatch log
    # streams.
    resources = [
      "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/aws/lambda/${var.name_prefix}-kb-ingestion-sync:*"
    ]
  }
}

resource "aws_iam_role_policy" "kb_ingestion_sync" {
  name   = "${var.name_prefix}-kb-ingestion-sync-policy"
  role   = aws_iam_role.kb_ingestion_sync.id
  policy = data.aws_iam_policy_document.kb_ingestion_sync_permissions.json
}
