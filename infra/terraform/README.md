# AMC RFP Orchestrator — Phase 02 Terraform (Amazon Bedrock AgentCore)

Infrastructure-only. Provisions every AWS resource the deployed system
needs (AgentCore Runtime/Gateway/Memory, ECR, DynamoDB, OpenSearch
Serverless + Bedrock Knowledge Base, Lambda tool stubs, IAM, observability),
modular across `dev`/`staging`/`prod`. See the root `CLAUDE.md`'s "Phase 02"
section for the architecture decisions this build locks in (network mode,
database choice, auth model, scope) and why.

**What this does NOT do**: build or push the agent's container image.
The AgentCore-compliant entrypoint (`src/amc_orchestrator/runtime_entrypoint.py`),
the DynamoDB/Bedrock-Knowledge-Base data-layer swap, and the repo-root
`Dockerfile` are now written (see `docs/architecture.md`'s "Phase 02" app-code
section and `docs/user_guide.md`'s "Deploying to AWS" section) - but
actually running `docker build`/`docker push` stays a manual or CI step,
never something Terraform does itself. This Terraform provisions the AWS
resources the app needs and surfaces the wiring (table names, endpoints,
role ARNs) via root outputs, consumed by `Settings`.

## Layout

```
bootstrap/                 one-time: S3 state bucket, its own local state
modules/                   reusable, environment-agnostic
environments/{dev,staging,prod}/   composes the modules, one per environment
```

## Prerequisites

- Terraform v1.15.7 (`terraform version` - this repo pins `>= 1.15.7, < 2.0.0`)
- AWS credentials for the target account (`aws configure` or an SSO profile)
- Bedrock model access already granted in the target account/region for
  the chosen `bedrock_model_id` and embedding model (Bedrock model access
  is an account-level opt-in done once in the console or via
  `aws bedrock` CLI, not something Terraform provisions)

## One-time: bootstrap the state backend

```powershell
cd infra/terraform/bootstrap
terraform init
terraform apply
```

This has its own local state (it can't remotely-store the state of the
bucket that state would live in). Note the `state_bucket_name` output -
every environment's backend config needs it.

## Per-environment apply — three phases

Each environment (`dev`/`staging`/`prod`) is applied in up to three passes,
because a handful of AWS resources genuinely can't be created before their
prerequisites exist yet. **Passes 2 and 3 are independent of each other and
can be done in either order** once their own prerequisite is met - only
pass 1 has to happen first.

### Pass 1 — everything that doesn't depend on a not-yet-existing artifact

```powershell
cd infra/terraform/environments/dev   # or staging / prod
cp backend.hcl.example backend.hcl    # fill in the bucket name from bootstrap's output
terraform init -backend-config=backend.hcl
terraform plan    # enable_knowledge_base and enable_agent_runtime default to false
terraform apply
```

Creates: IAM roles, ECR repo (empty), S3 docs bucket, DynamoDB table,
Lambda tool stubs, AgentCore Gateway + targets, AgentCore Memory,
observability (log groups/dashboard/alarms), and - only when
`vector_store_backend = "opensearch"` (the default; the only option in
staging/prod) - the OpenSearch Serverless collection + encryption/network/
data-access policies. When `vector_store_backend = "s3_vectors"` (dev-only),
none of the OpenSearch resources are created at all, even in this pass -
see "Pass 2" below.

### Pass 2 — vector index + Knowledge Base

Which vector store backs the Knowledge Base is controlled by
`var.vector_store_backend` (`"opensearch"` or `"s3_vectors"`) -
`environments/staging` and `environments/prod` hard-lock this to
`"opensearch"` (validation error if you try to change it); only
`environments/dev` can opt into `"s3_vectors"` for cost.

**`vector_store_backend = "opensearch"` (default, required in staging/prod):**

AWS OpenSearch Serverless has no native Terraform index resource in
`hashicorp/aws` (confirmed against the AWS-authored "Deploy Amazon
OpenSearch Serverless with Terraform" blog post, which stops at
collection+policies). `modules/opensearch-index` creates it via the
`opensearch-project/opensearch` community provider instead, signed for
AOSS (`aws_signature_service = "aoss"`). That provider needs the
collection's real endpoint, which only exists after pass 1.

Before this pass, add whoever/whatever is running `terraform apply` to
`additional_data_access_principals` in `terraform.tfvars` - AOSS data-plane
access is gated by its own access policy (created in pass 1 from
`modules/iam`'s role list plus this variable), not just IAM permissions.
Without it, index creation fails with an AOSS authorization error.

**`vector_store_backend = "s3_vectors"` (dev-only, cheapest option):**

`modules/s3-vectors` creates an S3 Vectors bucket + index directly via
`hashicorp/aws` (`aws_s3vectors_vector_bucket`/`aws_s3vectors_index`,
landed in provider `>= 6.27.0`) - a native resource, so unlike the
OpenSearch path there's no community provider and no
`additional_data_access_principals` step needed for this piece. The
OpenSearch Serverless collection itself (pass 1) and its access policy are
also skipped entirely with this backend - `modules/opensearch-serverless`
and `modules/opensearch-access-policy` gate their resources internally via
an `enabled` variable (not `count` on the module block, to keep every
consumer of their outputs - the `opensearch` provider block in particular -
a plain singleton-module reference rather than a `[0]`-indexed one), so
this backend creates **zero** OpenSearch resources for full cost savings.
See `docs/architecture.md`'s "Dev-only vector store choice" section for the
full design reasoning, including the `moved` blocks that keep this change
non-destructive for any environment that already had the collection
applied un-indexed.

```powershell
# after editing terraform.tfvars: enable_knowledge_base = true, plus
# (opensearch backend only) additional_data_access_principals
terraform apply
```

Creates: the vector index (`modules/opensearch-index` or `modules/s3-vectors`,
whichever `vector_store_backend` selects), the Bedrock Knowledge Base + S3
data source (`modules/knowledge-base`), empty, and the auto-sync pipeline
(`modules/kb-ingestion-sync` - an SQS queue + DLQ + Lambda wired to the docs
bucket's `s3:ObjectCreated:*`/`s3:ObjectRemoved:*` events, which calls
`bedrock-agent:StartIngestionJob` whenever a document changes). The *first*
upload of documents to the S3 docs bucket is still a separate, manual/CI
step (this Terraform only provisions the bucket, never populates it) - but
every upload/delete after that re-syncs the Knowledge Base automatically
within `maximum_batching_window_seconds` (default 5 minutes), no manual
`start_ingestion_job` call needed. See `modules/kb-ingestion-sync/main.tf`
for the SQS batching design and `modules/iam/kb_ingestion_sync_role.tf` for
why its `bedrock:StartIngestionJob` permission is wildcarded to
`knowledge-base/*` rather than scoped to one KB ARN (avoids the same
iam↔knowledge_base module cycle already solved once for OpenSearch's access
policy).

### Pass 3 — the agent runtime itself

`aws_bedrockagentcore_agent_runtime` requires a container image that
already exists in ECR. Terraform will never build or push one - build
your own image (from the app-code follow-on task's Dockerfile, once it
exists) and push it to the URL from pass 1's `ecr_repository_url` output:

```powershell
docker build -t <ecr_repository_url>:v1 .
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <ecr_repository_url>
docker push <ecr_repository_url>:v1
```

Then:

```powershell
# terraform.tfvars: enable_agent_runtime = true, container_image_uri = "<ecr_repository_url>:v1"
terraform apply
```

## CI/CD (GitHub Actions)

As of Phase 3, the manual commands in "Per-environment apply" above are
normally run through two GitHub Actions workflows instead of by hand -
`docker build`/`docker push`/`terraform apply` are still exactly the same
underlying operations, just automated. Full setup steps and the
`github-oidc/` module's design are in
[`docs/ci_cd_runbook.md`](../../docs/ci_cd_runbook.md); short version:

- **`.github/workflows/pr-validate.yml`** - runs automatically on every PR
  to `main`. Lint/type-check/unit tests for app changes, `terraform fmt`/
  `validate` (no AWS credentials) plus `terraform plan` posted as a PR
  comment (a read-only OIDC role) for infra changes, and a Docker build
  sanity check (no push). Never applies, never pushes an image.
- **`.github/workflows/deploy.yml`** - `workflow_dispatch` only, the *only*
  workflow that ever mutates AWS. Builds+pushes a fresh image to dev's ECR
  repo (dev target), promotes an already-built image into staging's/prod's
  ECR repo via `crane copy` with no rebuild (staging/prod targets, "build
  once, promote" - the same image is byte-identical everywhere it runs),
  then runs `terraform apply -var="container_image_uri=..."` for whichever
  environment was selected. `container_image_uri` is always supplied this
  way, never committed to tracked `terraform.tfvars` (see `infra/terraform/github-oidc/`'s
  design for why).
- Both workflows authenticate to AWS via **OIDC federated IAM roles**
  (`infra/terraform/github-oidc/`), not long-lived access-key secrets - one
  shared read-only role for PR-triggered plans, one per-environment
  write-scoped role for manual deploys. That module is applied once, by
  hand, before either workflow can run - see the runbook.

## Known gotchas

- **`VPC` network mode is deliberately not used.** `aws_bedrockagentcore_agent_runtime`
  in `VPC` mode creates ENIs that AWS locks with an "agentic_ai" owner,
  which cannot be detached or deleted - `terraform destroy` hangs forever
  on the VPC/subnet/ENI dependency cycle (confirmed:
  [terraform-provider-aws#45099](https://github.com/hashicorp/terraform-provider-aws/issues/45099),
  closed "not planned" - an AWS service-side limitation). Every module here
  uses `PUBLIC` network mode instead; access to DynamoDB/OpenSearch is
  scoped by IAM + the OpenSearch data-access policy.
- **`opensearch_index.mappings`/`index_knn` require the collection to
  already exist** - see "Pass 2" above; applying with
  `enable_knowledge_base = true` on a fresh environment (no pass 1 yet)
  will fail because `module.opensearch_serverless.collection_endpoint`
  isn't a real endpoint yet.
- **Alarms are opt-in per environment.** `alarm_email = ""` (the default)
  creates the SNS topic and alarms but subscribes nobody - set a real
  address before relying on them, especially in prod.
- **`terraform plan`/`apply` need real AWS credentials and the bootstrap
  bucket to exist.** `terraform validate` (schema/type checking, no
  credentials needed) is what CI or a quick sanity check should run instead
  - exactly the split `pr-validate.yml` uses (`tf-fmt-validate` needs no
    credentials, `tf-plan` needs the read-only OIDC role, see "CI/CD" above).
- **S3 Vectors IAM action names are plural ("Vectors"), not singular** -
  `modules/iam/knowledge_base_role.tf`'s `S3VectorsDataPlane` statement
  originally guessed singular (`GetVector`/`PutVector`/`DeleteVector`) from
  a third-party reference and failed with a real `AccessDenied` on
  `s3vectors:GetVectors` during a real dev apply (the KB service tries a
  read at creation time, not just during later ingestion) - fixed and
  confirmed against AWS's own IAM policy examples
  (`docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-iam-policies.html`).
  `modules/s3-vectors/variables.tf`'s `data_type`/`distance_metric`
  defaults (`"float32"`/`"cosine"`) are now confirmed to work too - the
  same apply successfully created the vector bucket and index with those
  values, before failing on the (now-fixed) IAM issue. Whether `"cosine"`
  is the *optimal* choice for retrieval quality (vs. just a valid one)
  is a separate, non-blocking question not yet investigated.
- **`modules/opensearch-serverless`/`modules/opensearch-access-policy` carry
  `moved.tf` files.** These exist because their resources gained `count =
  var.enabled ? 1 : 0` (to fully skip the collection when
  `vector_store_backend = "s3_vectors"`) - without the `moved` blocks,
  Terraform would treat the address change as a destroy+recreate of the
  whole collection on any environment that already had it applied
  un-indexed, not a harmless rename. Don't delete these files as "unused
  cleanup" without checking whether any environment's state still needs
  the migration path first.
- **Switching `vector_store_backend` on an environment that already has
  `enable_knowledge_base = true` applied is a two-step operation, not
  one.** Flipping the backend var while the Knowledge Base is enabled means
  the old backend's vector index/collection and the new backend's resources
  would need to be torn down and stood up in the same apply, which exercises
  the `opensearch` Terraform provider's configuration machinery in a way
  that isn't empirically verified. Set `enable_knowledge_base = false` and
  apply first (tears down the old backend cleanly), then flip
  `vector_store_backend` and re-enable in a second apply.

## Settings mapping (handoff to the app-code follow-on task)

These `terraform output` values become the container's process environment
variables (wired into `agent_runtime_artifact.environment_variables` in
`modules/agentcore-runtime`), which `config/settings.py`'s `Settings` class
reads directly - no env file needed in the deployed container. Done vs.
still-deferred (Gateway/Memory wiring into the agent graph was explicitly
scoped out - see `CLAUDE.md`'s Phase 02 notes):

| Terraform output                  | Settings field                    | Status |
|------------------------------------|------------------------------------|--------|
| `dynamodb_table_name`             | `dynamodb_table_name`             | done - `data/dynamodb_store.py` |
| `knowledge_base_id`               | `bedrock_knowledge_base_id`       | done - `data/knowledge_base_store.py` |
| `opensearch_collection_endpoint`  | *(none)*                          | not consumed directly - qual data goes through the Knowledge Base's `Retrieve` API instead of raw OpenSearch queries |
| `gateway_url`                     | *(none)*                          | deferred - agents still call tools in-process, not via the Gateway |
| `memory_id`                       | *(none)*                          | deferred - AgentCore Memory not yet wired into the graph |
| `kb_docs_bucket_name`             | *(none)*                          | not app config - the *initial* document upload is a separate manual/CI step, but ongoing sync after that is automatic (`modules/kb-ingestion-sync`) |
| `ecr_repository_url`              | *(none)*                          | CI/CD variable, not app config |
| `agent_runtime_arn`               | *(none)*                          | CI/CD variable, not app config |

## Adding a 4th environment

Copy `environments/dev/` (all files), rename to e.g. `environments/qa/`,
update `variables.tf`'s `environment` default + validation, adjust
`terraform.tfvars` for the new environment's cost/HA posture, and pick a
new `key` in its `backend.hcl`. No module changes needed - they're all
environment-agnostic.
