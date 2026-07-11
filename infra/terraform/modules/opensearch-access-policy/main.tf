# Split out from modules/opensearch-serverless deliberately: the data
# access policy's Principal list comes from modules/iam's role outputs, but
# modules/iam needs the collection's ARN as an input (to scope its aoss:*
# IAM statements) - so iam must be created from opensearch-serverless's
# outputs, and this policy must be created from iam's outputs. Combining
# both into one module would be a dependency cycle; see
# environments/*/main.tf for the actual apply order.
resource "aws_opensearchserverless_access_policy" "data" {
  name        = "${var.collection_name}-data"
  type        = "data"
  description = "Data-plane access for ${var.collection_name}"

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "index"
          Resource     = ["index/${var.collection_name}/*"]
          Permission   = ["aoss:*"]
        },
        {
          ResourceType = "collection"
          Resource     = ["collection/${var.collection_name}"]
          Permission   = ["aoss:*"]
        }
      ]
      Principal = var.principal_arns
    }
  ])
}
