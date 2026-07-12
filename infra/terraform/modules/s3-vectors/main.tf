# Amazon S3 Vectors - the cheapest vector store Bedrock Knowledge Base
# supports, used as a dev-only alternative to modules/opensearch-serverless
# + modules/opensearch-index (see environments/*/variables.tf's
# vector_store_backend). Unlike the OpenSearch index, the vector index here
# is a native hashicorp/aws resource - no community provider, no two-pass
# apply, no AOSS data-access-policy dance required to create it.

locals {
  bucket_name = "${var.name_prefix}-vectors-${var.account_id}"
}

resource "aws_kms_key" "vectors" {
  count                   = var.use_cmk ? 1 : 0
  description             = "CMK for ${local.bucket_name} S3 Vectors bucket"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = var.tags
}

resource "aws_kms_alias" "vectors" {
  count         = var.use_cmk ? 1 : 0
  name          = "alias/${var.name_prefix}-vectors"
  target_key_id = aws_kms_key.vectors[0].key_id
}

resource "aws_s3vectors_vector_bucket" "kb_vectors" {
  vector_bucket_name = local.bucket_name
  force_destroy      = true

  dynamic "encryption_configuration" {
    for_each = var.use_cmk ? [1] : []
    content {
      sse_type    = "aws:kms"
      kms_key_arn = aws_kms_key.vectors[0].arn
    }
  }

  tags = var.tags
}

resource "aws_s3vectors_index" "kb_vector_index" {
  vector_bucket_name = aws_s3vectors_vector_bucket.kb_vectors.vector_bucket_name
  index_name         = var.index_name
  data_type          = var.data_type
  dimension          = var.embedding_dimension
  distance_metric    = var.distance_metric

  dynamic "metadata_configuration" {
    for_each = length(var.non_filterable_metadata_keys) > 0 ? [1] : []
    content {
      non_filterable_metadata_keys = var.non_filterable_metadata_keys
    }
  }
}
