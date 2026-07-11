provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

# Only ever actually configured/connected-to when module.knowledge_base's
# count is 1 (enable_knowledge_base = true) and the collection already
# exists from a prior apply - see README.md's phased-apply section. Not
# used at all during the first apply, so its endpoint being unknown at that
# point is harmless: Terraform never calls Configure() on a provider no
# resource in the current graph actually needs.
provider "opensearch" {
  url                   = module.opensearch_serverless.collection_endpoint
  aws_region            = var.aws_region
  sign_aws_requests     = true
  aws_signature_service = "aoss"
  healthcheck           = false
}
