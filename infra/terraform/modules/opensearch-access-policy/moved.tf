# See modules/opensearch-serverless/moved.tf for the full rationale - this
# resource gained `count = var.enabled ? 1 : 0` for the same reason.

moved {
  from = aws_opensearchserverless_access_policy.data
  to   = aws_opensearchserverless_access_policy.data[0]
}
