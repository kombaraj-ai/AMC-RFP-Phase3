# These three resources gained `count = var.enabled ? 1 : 0` when
# vector_store_backend = "s3_vectors" support was added (dev-only cost
# optimization - see environments/dev/variables.tf). Without these `moved`
# blocks, Terraform would treat the un-indexed -> [0] address change as a
# destroy+recreate of the whole collection on any environment that already
# had it applied, instead of a harmless rename. Safe to keep indefinitely -
# a `moved` block is a no-op once the state has already been migrated.

moved {
  from = aws_opensearchserverless_security_policy.encryption
  to   = aws_opensearchserverless_security_policy.encryption[0]
}

moved {
  from = aws_opensearchserverless_security_policy.network
  to   = aws_opensearchserverless_security_policy.network[0]
}

moved {
  from = aws_opensearchserverless_collection.kb_vectors
  to   = aws_opensearchserverless_collection.kb_vectors[0]
}
