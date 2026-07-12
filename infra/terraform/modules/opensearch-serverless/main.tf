locals {
  # AWS caps OpenSearch Serverless collection AND security/access policy
  # names at 32 characters - and the policies below append "-enc"/"-net"
  # (4 chars) or "-data" (5 chars, in modules/opensearch-access-policy) to
  # this base name. 32 - 5 = 27 is the safe budget for the base itself.
  #
  # A naive substr() truncation risks two environments colliding if
  # var.name_prefix is long enough that truncation cuts off the part that
  # made them different (e.g. the "-staging"/"-prod" suffix) - so when
  # truncation is actually needed, a short hash of the untruncated name is
  # appended to guarantee uniqueness survives instead of silently breaking.
  collection_name_full = "${var.name_prefix}-vec"
  collection_name      = length(local.collection_name_full) <= 27 ? local.collection_name_full : "${substr(local.collection_name_full, 0, 20)}-${substr(md5(local.collection_name_full), 0, 6)}"
}

resource "aws_opensearchserverless_security_policy" "encryption" {
  count = var.enabled ? 1 : 0

  name        = "${local.collection_name}-enc"
  type        = "encryption"
  description = "Encryption policy for ${local.collection_name}"

  # AWS rejects a literal null for the key not in use, so the two branches
  # build genuinely different object shapes rather than nulling out a field.
  policy = var.use_cmk ? jsonencode({
    Rules = [
      {
        Resource     = ["collection/${local.collection_name}"]
        ResourceType = "collection"
      }
    ]
    KmsARN = var.kms_key_arn
    }) : jsonencode({
    Rules = [
      {
        Resource     = ["collection/${local.collection_name}"]
        ResourceType = "collection"
      }
    ]
    AWSOwnedKey = true
  })
}

# PUBLIC network mode was chosen for the AgentCore Runtime (see the module's
# own comments and infra/terraform/README.md for the ENI-lock/destroy-hang
# bug this avoids) - the collection's network policy mirrors that: reachable
# over the public AOSS endpoint, with actual authorization enforced by the
# data access policy below and by IAM on every caller, not by network
# isolation.
resource "aws_opensearchserverless_security_policy" "network" {
  count = var.enabled ? 1 : 0

  name        = "${local.collection_name}-net"
  type        = "network"
  description = "Public network policy for ${local.collection_name} (PUBLIC runtime network mode)"

  policy = jsonencode([
    {
      Description = "Public access to ${local.collection_name} collection and dashboards"
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${local.collection_name}"]
        },
        {
          ResourceType = "dashboard"
          Resource     = ["collection/${local.collection_name}"]
        }
      ]
      AllowFromPublic = true
    }
  ])
}

resource "aws_opensearchserverless_collection" "kb_vectors" {
  count = var.enabled ? 1 : 0

  name             = local.collection_name
  type             = "VECTORSEARCH"
  standby_replicas = var.standby_replicas

  tags = var.tags

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network,
  ]
}
