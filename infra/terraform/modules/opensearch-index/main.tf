# Deliberately a standalone module, applied in a documented second pass
# (see infra/terraform/README.md) - AWS OpenSearch Serverless has no native
# Terraform index resource in hashicorp/aws (confirmed: the official AWS
# collection-deployment blog stops at collection+policies and does not
# create indices), so this uses the opensearch-project/opensearch community
# provider's resource against the collection's AOSS endpoint. The `opensearch`
# provider must be configured in the calling root module with
# aws_signature_service = "aoss" (not the "es" default) and passed in
# explicitly via `providers = { opensearch = opensearch.aoss }` - it can't be
# configured inside this module because its endpoint is only known after
# modules/opensearch-serverless's collection has actually been created,
# which is exactly the chicken-and-egg this second-pass apply works around.

resource "opensearch_index" "kb_vector_index" {
  name      = var.index_name
  index_knn = true

  mappings = jsonencode({
    properties = {
      (var.vector_field) = {
        type      = "knn_vector"
        dimension = var.embedding_dimension
        method = {
          name       = "hnsw"
          engine     = "faiss"
          space_type = "l2"
        }
      }
      (var.text_field) = {
        type  = "text"
        index = true
      }
      (var.metadata_field) = {
        type  = "text"
        index = false
      }
    }
  })
}
