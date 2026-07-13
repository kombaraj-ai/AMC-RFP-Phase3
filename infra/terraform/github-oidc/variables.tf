variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "amc-orchestrator"
}

variable "github_org" {
  description = "GitHub organization or user that owns the repository, e.g. \"my-org\" in \"my-org/amc-orchestrator\". Scopes the OIDC trust policies' `sub` claim condition - see oidc_provider.tf/plan_role.tf/deploy_role.tf."
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name only, without the org, e.g. \"amc-orchestrator\"."
  type        = string
}

variable "state_bucket_name" {
  description = "The Terraform state bucket infra/terraform/bootstrap already created (terraform -chdir=infra/terraform/bootstrap output state_bucket_name). Each deploy role gets read/write access scoped to its own environment's object-key prefix in this bucket."
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
