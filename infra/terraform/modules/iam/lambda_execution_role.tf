# --- lambda_execution_role -------------------------------------------------
# Assumed by the stub tool Lambdas (modules/lambda-tools). Scoped to exactly
# what the real tool implementations will need later: read/write the quant
# table, read/query the OpenSearch collection, write their own logs.

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_execution" {
  name               = "${var.name_prefix}-lambda-tools-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    sid       = "DynamoDbQuantMetrics"
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:Query"]
    resources = [var.dynamodb_table_arn, "${var.dynamodb_table_arn}/index/*"]
  }

  dynamic "statement" {
    for_each = var.opensearch_collection_arn != "" ? [1] : []
    content {
      sid       = "OpenSearchServerlessDataPlane"
      effect    = "Allow"
      actions   = ["aoss:APIAccessAll"]
      resources = [var.opensearch_collection_arn]
    }
  }

  statement {
    sid     = "CloudWatchLogsOwnFunctions"
    effect  = "Allow"
    actions = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:CreateLogGroup"]
    resources = [
      "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/aws/lambda/${var.name_prefix}-*"
    ]
  }
}

resource "aws_iam_role_policy" "lambda_execution" {
  name   = "${var.name_prefix}-lambda-tools-policy"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}
