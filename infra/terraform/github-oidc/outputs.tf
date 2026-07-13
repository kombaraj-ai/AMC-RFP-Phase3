output "plan_role_arn" {
  description = "Paste into GitHub repo Settings -> Secrets and variables -> Actions -> Variables, as the repo-level AWS_PLAN_ROLE_ARN. Read-only; used by pr-validate.yml's tf-plan job on every PR."
  value       = aws_iam_role.plan.arn
}

output "deploy_role_arns" {
  description = "One ARN per environment. Paste each into the matching GitHub Environment's (dev/staging/prod) AWS_DEPLOY_ROLE_ARN variable. Used only by deploy.yml, which is workflow_dispatch-only."
  value       = { for env, role in aws_iam_role.deploy : env => role.arn }
}

output "github_oidc_provider_arn" {
  value = aws_iam_openid_connect_provider.github_actions.arn
}
