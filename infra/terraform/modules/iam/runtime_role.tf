# --- agentcore_runtime_role ---------------------------------------------
# Assumed by the AgentCore Runtime service to run the agent container and
# reach the app's own dependencies (DynamoDB, OpenSearch, Bedrock models,
# ECR, logs). No wildcard resource ARNs.

data "aws_iam_policy_document" "runtime_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.account_id]
    }
  }
}

resource "aws_iam_role" "runtime" {
  name               = "${var.name_prefix}-agentcore-runtime-role"
  assume_role_policy = data.aws_iam_policy_document.runtime_trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "runtime_permissions" {
  statement {
    sid       = "DynamoDbQuantMetrics"
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"]
    resources = [var.dynamodb_table_arn, "${var.dynamodb_table_arn}/index/*"]
  }

  statement {
    sid       = "OpenSearchServerlessDataPlane"
    effect    = "Allow"
    actions   = ["aoss:APIAccessAll"]
    resources = [var.opensearch_collection_arn]
  }

  statement {
    sid       = "InvokeBedrockModels"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = var.bedrock_model_arns
  }

  statement {
    sid     = "CloudWatchLogs"
    effect  = "Allow"
    actions = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:CreateLogGroup", "logs:DescribeLogStreams"]
    resources = [
      "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/amc-orchestrator/${var.name_prefix}/*"
    ]
  }

  statement {
    sid    = "EcrPullRuntimeImage"
    effect = "Allow"
    actions = [
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:BatchCheckLayerAvailability",
    ]
    resources = [var.ecr_repository_arn]
  }

  statement {
    sid       = "EcrAuth"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # GetAuthorizationToken does not support resource-level scoping.
  }
}

resource "aws_iam_role_policy" "runtime" {
  name   = "${var.name_prefix}-agentcore-runtime-policy"
  role   = aws_iam_role.runtime.id
  policy = data.aws_iam_policy_document.runtime_permissions.json
}
