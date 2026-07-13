# --- github_actions_oidc -----------------------------------------------
# One-time, account-wide OIDC trust anchor for GitHub Actions. Every role in
# this module (plan_role.tf, deploy_role.tf) federates through this same
# provider - GitHub signs a short-lived JWT per workflow run, AWS verifies it
# against this provider, no long-lived AWS credentials are ever stored in
# GitHub (the explicit reason this project chose OIDC over access-key
# secrets - see infra/terraform/README.md's CI/CD section).

# Fetches GitHub's current OIDC signing-certificate thumbprint directly
# rather than hardcoding it - the pattern the Terraform AWS provider's own
# docs recommend for this exact resource. Avoids silently going stale if
# GitHub ever rotates their CA (a real, historical event for this specific
# provider), unlike a hardcoded thumbprint value baked into the config.
data "tls_certificate" "github_actions" {
  url = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github_actions.certificates[0].sha1_fingerprint]

  tags = local.common_tags
}
