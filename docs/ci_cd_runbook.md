# CI/CD runbook (Phase 3)

This is the GitHub-side setup for `.github/workflows/pr-validate.yml` and
`.github/workflows/deploy.yml`, plus the sequence for staging/prod's very
first apply (they have never been applied - see root `CLAUDE.md`). None of
this is Terraform-managed - see "Why GitHub Environments aren't
Terraform-managed" below for why.

For the workflows' own design (triggers, jobs, IAM/OIDC model), see
`infra/terraform/README.md`'s "CI/CD" section and the two workflow files
themselves - this doc is the one-time manual setup and the runbook
sequence, not the design rationale.

## 1. One-time: apply `infra/terraform/github-oidc/`

Run locally, with your own AWS credentials - this is the one piece of CI
infrastructure that can't bootstrap itself (CI can't create the very IAM
role it needs to authenticate).

```powershell
cd infra/terraform/github-oidc
cp backend.hcl.example backend.hcl        # fill in the bucket name from bootstrap's output
cp terraform.tfvars.example terraform.tfvars   # fill in github_org / github_repo / state_bucket_name
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
terraform output deploy_role_arns
terraform output plan_role_arn
```

Keep those output values handy for step 3.

## 2. One-time: create GitHub Environments

In the repo's Settings → Environments, create three Environments named
exactly `dev`, `staging`, `prod` (these names must match `deploy.yml`'s
`environment:` inputs and `github-oidc`'s trust-policy `sub` claims
exactly). For each:

- **Deployment branches**: restrict to `main` only. This is the actual
  safety net for "nothing deploys from a random branch" now that there's no
  required-reviewer approval gate (see below) - it costs nothing and needs
  no extra credential, unlike Terraform-managing this via a GitHub PAT.
- **No required reviewers.** GitHub does not let the person who triggered a
  workflow run approve their own deployment - on a single-maintainer
  project, adding a required-reviewer rule here would deadlock every
  staging/prod deploy unless a second GitHub account is always available to
  click approve. The manual `workflow_dispatch` trigger + OIDC
  environment-scoped role + the branch restriction above are the safety net
  instead. Revisit this if a second maintainer ever joins.

## 3. One-time: set repo/Environment variables

Settings → Secrets and variables → Actions → Variables.

**Repo-level** (used by `pr-validate.yml`'s `tf-plan` job, which never
declares an `environment:` - see `infra/terraform/github-oidc/plan_role.tf`
for why this is deliberately repo-level, not Environment-scoped):

| Name | Value |
|---|---|
| `AWS_PLAN_ROLE_ARN` | `terraform output plan_role_arn` from step 1 |
| `TF_STATE_BUCKET` | `terraform -chdir=infra/terraform/bootstrap output state_bucket_name` |

**Per-Environment** (set once inside each of the `dev`/`staging`/`prod`
Environments created in step 2 - same variable name, different value per
Environment, resolved automatically since `deploy.yml`'s jobs declare
`environment: <input>`):

| Name | dev value | staging value | prod value |
|---|---|---|---|
| `AWS_DEPLOY_ROLE_ARN` | `deploy_role_arns["dev"]` | `deploy_role_arns["staging"]` | `deploy_role_arns["prod"]` |

(All from step 1's `terraform output deploy_role_arns`.)

## 4. Staging/prod first-ever rollout

Both environments have never been applied - empty state, no `backend.hcl`
yet. Every step below uses the same generic `deploy.yml` - only tfvars
content and the workflow's inputs change per pass, there is no special
pipeline logic for "first apply" vs. "steady state".

1. Open a PR fixing the EOL `bedrock_model_id` in
   `infra/terraform/environments/staging/terraform.tfvars` (already done as
   part of this phase - verify it reads `"amazon.nova-lite-v1:0"`). Merge
   after `pr-validate.yml` passes.
2. **Pass 1 (staging):** Actions → Deploy → Run workflow →
   `environment=staging`, `promote_image=false`. `build-and-push`/`promote`
   both skip (only run for their respective targets); `terraform-apply`
   applies staging's tfvars as committed (`enable_knowledge_base=false`,
   `enable_agent_runtime=false`) - creates IAM roles, ECR repo, DynamoDB,
   S3 docs bucket, Lambda stubs, Gateway, Memory, observability, and the
   OpenSearch Serverless collection (staging is `opensearch`-only, unlike
   dev's `s3_vectors` option).
3. PR: set staging's `additional_data_access_principals` to the
   `deploy-staging` role ARN from step 1 (staging's tfvars already has a
   comment marking exactly where), and `enable_knowledge_base = true`.
   Merge after `pr-validate.yml` passes.
4. **Pass 2 (staging):** dispatch `deploy.yml` again, same inputs as step 2
   above (`environment=staging`, `promote_image=false`) - creates the
   vector index, the Bedrock Knowledge Base, and the ingestion-sync
   pipeline.
5. Ensure a current image exists in dev: dispatch `deploy.yml` with
   `environment=dev` (builds+pushes, tagged with the full commit SHA). Note
   that SHA from the run's logs or from `git rev-parse HEAD` on the commit
   you dispatched from.
6. PR: set staging's `enable_agent_runtime = true` (leave
   `container_image_uri` alone - it's always supplied via `-var` at apply
   time, never committed). Merge after `pr-validate.yml` passes.
7. **Pass 3 (staging):** dispatch `deploy.yml` with `environment=staging`,
   `promote_image=true`, `image_tag=<the SHA from step 5>` - promotes that
   exact dev-built image into staging's ECR repo, then applies with
   `enable_agent_runtime=true`.
8. Smoke-test staging (same `invoke_agent_runtime` pattern documented in
   root `CLAUDE.md`/`docs/user_guide.md` for dev).
9. Repeat steps 1-7 for `prod` once staging is verified working - the first
   document upload to prod's S3 docs bucket (pass 2) is still a manual/CI
   step Terraform doesn't do (see `infra/terraform/README.md`'s "Pass 2"),
   same as it was for dev/staging.

## Why GitHub Environments aren't Terraform-managed

Codifying Environments/protection-rules/variables via Terraform would need
the `integrations/github` provider, which needs its own GitHub PAT or
GitHub App credential - a whole new credential surface for a one-time,
rarely-changed setting. For a single-maintainer project that's not a good
trade; the manual steps above are simple enough to redo by hand if ever
needed (e.g. after transferring the repo to a new org).
