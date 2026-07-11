# --- agentcore_gateway_role ----------------------------------------------
# Assumed by the AgentCore Gateway service to invoke Lambda gateway targets.
#
# Lambda function ARNs are constructed from the shared naming convention
# (name_prefix + tool name) rather than taken as a module-output variable
# from modules/lambda-tools, deliberately - modules/lambda-tools takes this
# module's lambda_execution_role output as an input, so threading the
# reverse dependency (lambda ARNs back into this module) would create a
# module dependency cycle. Both modules derive the same ARN from the same
# inputs instead; see environments/*/main.tf where var.lambda_tool_names is
# passed identically to both.

data "aws_iam_policy_document" "gateway_trust" {
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

resource "aws_iam_role" "gateway" {
  name               = "${var.name_prefix}-agentcore-gateway-role"
  assume_role_policy = data.aws_iam_policy_document.gateway_trust.json
  tags               = var.tags
}

locals {
  lambda_tool_arns = [
    for name in var.lambda_tool_names :
    "arn:aws:lambda:${var.aws_region}:${var.account_id}:function:${var.name_prefix}-${name}"
  ]
}

data "aws_iam_policy_document" "gateway_permissions" {
  statement {
    sid       = "InvokeLambdaTargets"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = local.lambda_tool_arns
  }

  statement {
    sid     = "CloudWatchLogs"
    effect  = "Allow"
    actions = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:CreateLogGroup", "logs:DescribeLogStreams"]
    resources = [
      "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/amc-orchestrator/${var.name_prefix}/*"
    ]
  }
}

resource "aws_iam_role_policy" "gateway" {
  name   = "${var.name_prefix}-agentcore-gateway-policy"
  role   = aws_iam_role.gateway.id
  policy = data.aws_iam_policy_document.gateway_permissions.json
}
