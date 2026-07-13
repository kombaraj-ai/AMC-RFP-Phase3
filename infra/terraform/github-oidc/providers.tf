provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

# Used only to fetch GitHub's current OIDC signing-certificate thumbprint -
# see oidc_provider.tf. Not an AWS provider; needs no credentials of its own.
provider "tls" {}
