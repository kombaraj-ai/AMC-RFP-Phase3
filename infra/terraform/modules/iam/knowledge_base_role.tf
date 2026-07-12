# --- knowledge_base_role ----------------------------------------------------
# Assumed by the Bedrock Knowledge Base service to read source docs from S3,
# call the embedding model, and read/write the OpenSearch Serverless vector
# index during ingestion and query.

data "aws_iam_policy_document" "kb_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.account_id]
    }
  }
}

resource "aws_iam_role" "knowledge_base" {
  name               = "${var.name_prefix}-knowledge-base-role"
  assume_role_policy = data.aws_iam_policy_document.kb_trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "kb_permissions" {
  statement {
    sid       = "ReadSourceDocs"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [var.kb_docs_bucket_arn, "${var.kb_docs_bucket_arn}/*"]
  }

  statement {
    sid       = "InvokeEmbeddingModel"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel"]
    resources = var.bedrock_model_arns
  }

  dynamic "statement" {
    for_each = var.opensearch_collection_arn != "" ? [1] : []
    content {
      sid       = "OpenSearchServerlessDataPlane"
      effect    = "Allow"
      actions   = ["aoss:APIAccessAll"]
      resources = [var.opensearch_collection_arn]
    }
  }

  # S3 Vectors data-plane access (dev-only backend, see
  # environments/dev/variables.tf's vector_store_backend). Action list taken
  # from AWS's own S3-Vectors-for-Bedrock reference examples, NOT
  # independently verified against AWS's Service Authorization Reference
  # (docs.aws.amazon.com/service-authorization/latest/reference/list_amazons3vectors.html)
  # - confirm there before relying on this outside of dev experimentation,
  # per this project's own precedent (CLAUDE.md's M0 note) of verifying
  # against real sources rather than blog posts.
  dynamic "statement" {
    for_each = var.s3_vectors_bucket_arn != "" ? [1] : []
    content {
      sid    = "S3VectorsDataPlane"
      effect = "Allow"
      actions = [
        "s3vectors:GetVector",
        "s3vectors:PutVector",
        "s3vectors:DeleteVector",
        "s3vectors:QueryVectors",
        "s3vectors:ListVectors",
        "s3vectors:GetIndex",
        "s3vectors:ListIndexes",
      ]
      resources = [var.s3_vectors_bucket_arn, "${var.s3_vectors_bucket_arn}/*"]
    }
  }
}

resource "aws_iam_role_policy" "knowledge_base" {
  name   = "${var.name_prefix}-knowledge-base-policy"
  role   = aws_iam_role.knowledge_base.id
  policy = data.aws_iam_policy_document.kb_permissions.json
}
