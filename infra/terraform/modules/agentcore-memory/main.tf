resource "aws_bedrockagentcore_memory" "rfp_sessions" {
  name                  = "${replace(var.name_prefix, "-", "_")}_rfp_sessions"
  event_expiry_duration = var.event_expiry_days
  encryption_key_arn    = var.use_cmk ? var.kms_key_arn : null
  tags                  = var.tags
}

# Semantic strategy so an RFP session's earlier turns (e.g. which fund the
# client already asked about) stay retrievable across the same session's
# later turns, without re-sending the full transcript to the model each time.
resource "aws_bedrockagentcore_memory_strategy" "semantic" {
  name        = "${replace(var.name_prefix, "-", "_")}_semantic"
  memory_id   = aws_bedrockagentcore_memory.rfp_sessions.id
  type        = "SEMANTIC"
  description = "Semantic recall across an RFP session's turns"
  namespaces  = ["{sessionId}"]
}
