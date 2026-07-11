# Runtime/Gateway CloudWatch log groups. Names match the pattern the IAM
# module's CloudWatchLogs statements grant write access to
# (/amc-orchestrator/{name_prefix}/*) - keep these in sync if either side
# changes.
resource "aws_cloudwatch_log_group" "runtime" {
  name              = "/amc-orchestrator/${var.name_prefix}/agent-runtime"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "gateway" {
  name              = "/amc-orchestrator/${var.name_prefix}/gateway"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_sns_topic" "alarms" {
  name = "${var.name_prefix}-amc-alarms"
  tags = var.tags
}

resource "aws_sns_topic_subscription" "alarm_email" {
  count     = var.alarm_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = toset(var.lambda_function_names)

  # each.value is already the fully-prefixed Lambda function name (from
  # modules/lambda-tools' function_names output) - prepending name_prefix
  # again here double-prefixes the alarm (caught via a live AWS check:
  # "amc-orchestrator-dev-amc-orchestrator-dev-quant-tools-errors").
  alarm_name          = "${each.value}-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = var.lambda_error_alarm_threshold
  treat_missing_data  = "notBreaching"
  alarm_description   = "${each.value} Lambda errors >= ${var.lambda_error_alarm_threshold} in 5 minutes"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]

  dimensions = {
    FunctionName = each.value
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "dynamodb_throttles" {
  alarm_name          = "${var.name_prefix}-quant-metrics-throttles"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ThrottledRequests"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = var.dynamodb_throttle_alarm_threshold
  treat_missing_data  = "notBreaching"
  alarm_description   = "DynamoDB table ${var.dynamodb_table_name} is being throttled"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]

  dimensions = {
    TableName = var.dynamodb_table_name
  }

  tags = var.tags
}

resource "aws_cloudwatch_dashboard" "amc_orchestrator" {
  dashboard_name = "${var.name_prefix}-amc-orchestrator"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Lambda tool errors"
          region  = var.aws_region
          metrics = [for name in var.lambda_function_names : ["AWS/Lambda", "Errors", "FunctionName", name]]
          stat    = "Sum"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "DynamoDB capacity + throttles"
          region = var.aws_region
          metrics = [
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", var.dynamodb_table_name],
            ["AWS/DynamoDB", "ConsumedWriteCapacityUnits", "TableName", var.dynamodb_table_name],
            ["AWS/DynamoDB", "ThrottledRequests", "TableName", var.dynamodb_table_name],
          ]
          stat   = "Sum"
          period = 300
        }
      },
    ]
  })
}
