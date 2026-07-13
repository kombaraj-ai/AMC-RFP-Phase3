terraform {
  required_version = ">= 1.15.7, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.20.0, < 7.0.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = ">= 4.0.0, < 5.0.0"
    }
  }

  # Reuses the state bucket infra/terraform/bootstrap already created - unlike
  # bootstrap itself, this module has no chicken-and-egg problem with its own
  # state (the bucket already exists by the time this is applied), so it can
  # safely use it as a normal remote backend. Real values come from
  # `terraform init -backend-config=backend.hcl` - see backend.hcl.example.
  backend "s3" {
    use_lockfile = true
  }
}
