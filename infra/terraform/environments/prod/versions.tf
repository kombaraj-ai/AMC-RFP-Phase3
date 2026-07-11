terraform {
  required_version = ">= 1.15.7, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.20.0, < 7.0.0"
    }
    opensearch = {
      source  = "opensearch-project/opensearch"
      version = ">= 2.3.2, < 3.0.0"
    }
  }

  # Partial backend config - real values (bucket, key, region) come from
  # `terraform init -backend-config=backend.hcl`, generated from
  # bootstrap's outputs. See infra/terraform/README.md.
  backend "s3" {
    use_lockfile = true
  }
}
