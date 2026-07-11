data "aws_caller_identity" "current" {}

locals {
  name_prefix = "${var.project}-${var.environment}"

  common_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  # Claude for generation + the chosen embedding model for the Knowledge
  # Base - both need to be invokable by the runtime/KB roles.
  bedrock_model_arns = [
    "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_model_id}",
    "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.embedding_model == "titan-v2" ? "amazon.titan-embed-text-v2:0" : "cohere.embed-multilingual-v3"}",
  ]
}
