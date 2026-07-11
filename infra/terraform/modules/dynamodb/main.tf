# Mirrors src/amc_orchestrator/data/sqlite_store.py's `fund_performance`
# table: `ticker` is the only declared key, every other quant field
# (fund_name, fund_category, nav, alpha, beta, sharpe_ratio, ...) is
# schemaless per DynamoDB's item-level attribute model and needs no
# Terraform-side declaration.

resource "aws_kms_key" "table" {
  count                   = var.use_cmk ? 1 : 0
  description             = "CMK for ${var.name_prefix}-quant-metrics DynamoDB table"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = var.tags
}

resource "aws_kms_alias" "table" {
  count         = var.use_cmk ? 1 : 0
  name          = "alias/${var.name_prefix}-quant-metrics"
  target_key_id = aws_kms_key.table[0].key_id
}

resource "aws_dynamodb_table" "quant_metrics" {
  name         = "${var.name_prefix}-quant-metrics"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "ticker"

  attribute {
    name = "ticker"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.point_in_time_recovery_enabled
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.use_cmk ? aws_kms_key.table[0].arn : null
  }

  deletion_protection_enabled = var.deletion_protection_enabled

  tags = var.tags
}
