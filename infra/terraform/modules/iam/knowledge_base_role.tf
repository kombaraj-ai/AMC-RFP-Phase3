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

  statement {
    sid       = "OpenSearchServerlessDataPlane"
    effect    = "Allow"
    actions   = ["aoss:APIAccessAll"]
    resources = [var.opensearch_collection_arn]
  }
}

resource "aws_iam_role_policy" "knowledge_base" {
  name   = "${var.name_prefix}-knowledge-base-policy"
  role   = aws_iam_role.knowledge_base.id
  policy = data.aws_iam_policy_document.kb_permissions.json
}
