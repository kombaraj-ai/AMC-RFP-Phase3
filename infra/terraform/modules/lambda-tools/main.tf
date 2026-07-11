data "archive_file" "stub" {
  type        = "zip"
  source_dir  = "${path.module}/stub_src"
  output_path = "${path.module}/.build/stub.zip"
}

resource "aws_cloudwatch_log_group" "tool" {
  for_each = toset(var.tool_names)

  name              = "/aws/lambda/${var.name_prefix}-${each.value}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_lambda_function" "tool" {
  for_each = toset(var.tool_names)

  function_name = "${var.name_prefix}-${each.value}"
  role          = var.lambda_execution_role_arn
  handler       = "handler.handler"
  runtime       = "python3.13"
  memory_size   = var.memory_size
  timeout       = var.timeout_seconds

  filename         = data.archive_file.stub.output_path
  source_code_hash = data.archive_file.stub.output_base64sha256

  environment {
    variables = {
      TOOL_NAME                      = each.value
      DYNAMODB_TABLE_NAME            = var.dynamodb_table_name
      OPENSEARCH_COLLECTION_ENDPOINT = var.opensearch_collection_endpoint
    }
  }

  tags = var.tags

  depends_on = [aws_cloudwatch_log_group.tool]
}
