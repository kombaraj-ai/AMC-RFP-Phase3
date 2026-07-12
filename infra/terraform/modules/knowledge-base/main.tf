locals {
  embedding_model_id = {
    titan-v2            = "amazon.titan-embed-text-v2:0"
    cohere-multilingual = "cohere.embed-multilingual-v3"
  }[var.embedding_model]

  embedding_model_arn = "arn:aws:bedrock:${var.aws_region}::foundation-model/${local.embedding_model_id}"
}

resource "aws_bedrockagent_knowledge_base" "fund_commentary" {
  name     = "${var.name_prefix}-fund-commentary-kb"
  role_arn = var.knowledge_base_role_arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = local.embedding_model_arn
    }
  }

  storage_configuration {
    type = var.vector_store_backend == "opensearch" ? "OPENSEARCH_SERVERLESS" : "S3_VECTORS"

    dynamic "opensearch_serverless_configuration" {
      for_each = var.vector_store_backend == "opensearch" ? [1] : []
      content {
        collection_arn    = var.opensearch_collection_arn
        vector_index_name = var.vector_index_name
        field_mapping {
          vector_field   = var.vector_field
          text_field     = var.text_field
          metadata_field = var.metadata_field
        }
      }
    }

    dynamic "s3_vectors_configuration" {
      for_each = var.vector_store_backend == "s3_vectors" ? [1] : []
      content {
        vector_bucket_arn = var.s3_vectors_bucket_arn
        index_arn         = var.s3_vectors_index_arn
        index_name        = var.s3_vectors_index_name
      }
    }
  }

  tags = var.tags

  lifecycle {
    precondition {
      condition     = var.vector_store_backend != "opensearch" || var.opensearch_collection_arn != ""
      error_message = "opensearch_collection_arn is required when vector_store_backend = \"opensearch\"."
    }
    precondition {
      condition     = var.vector_store_backend != "s3_vectors" || (var.s3_vectors_bucket_arn != "" && var.s3_vectors_index_arn != "" && var.s3_vectors_index_name != "")
      error_message = "s3_vectors_bucket_arn, s3_vectors_index_arn, and s3_vectors_index_name are all required when vector_store_backend = \"s3_vectors\"."
    }
  }
}

resource "aws_bedrockagent_data_source" "fund_commentary_docs" {
  knowledge_base_id    = aws_bedrockagent_knowledge_base.fund_commentary.id
  name                 = "${var.name_prefix}-fund-commentary-docs"
  data_deletion_policy = var.data_deletion_policy

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn = var.docs_bucket_arn
    }
  }

  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"
      fixed_size_chunking_configuration {
        max_tokens         = var.chunking_max_tokens
        overlap_percentage = var.chunking_overlap_percentage
      }
    }
  }
}
