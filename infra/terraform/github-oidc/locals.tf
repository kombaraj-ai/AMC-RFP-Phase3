data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id

  common_tags = merge(var.tags, {
    Project   = var.project
    ManagedBy = "terraform"
    Component = "github-oidc"
  })
}
