terraform {
  required_version = ">= 1.15.7, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.20.0, < 7.0.0"
    }
  }

  # Intentionally local state: this bucket is what every other root module's
  # remote state lives in, so it can't depend on itself. Apply this module
  # once, by hand, before anything else. See infra/terraform/README.md.
}
