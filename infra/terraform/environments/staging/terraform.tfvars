aws_region  = "us-east-1"
project     = "amc-orchestrator"
environment = "staging"

# --- Phased-apply gates: leave both false on the first apply -------------
enable_knowledge_base = false
enable_agent_runtime  = false
container_image_uri   = ""

# --- Cost/HA knobs - mirrors prod's security posture, still single-region -
use_cmk                         = true
opensearch_standby_replicas     = "ENABLED"
dynamodb_point_in_time_recovery = true
dynamodb_deletion_protection    = true
log_retention_days              = 90
memory_event_expiry_days        = 30
ecr_untagged_image_expiry_days  = 14
ecr_max_tagged_images           = 20
alarm_email                     = ""

# --- Model choices ----------------------------------------------------------
# anthropic.claude-3-5-sonnet-20241022-v2:0 reached end-of-life on Bedrock
# (confirmed live against dev, 2026-07-12 - see CLAUDE.md). Matches dev's
# already-proven value.
bedrock_model_id = "amazon.nova-lite-v1:0"
embedding_model  = "titan-v2"
runtime_protocol = "HTTP"

# Add the deploy-staging role's ARN here before the enable_knowledge_base=true
# pass, or vector-index creation will fail with an AOSS authorization error -
# see README.md and docs/ci_cd_runbook.md's first-time rollout sequence. This
# should be infra/terraform/github-oidc's deploy_role_arns["staging"] output
# (a CI/CD role), not a human's personal ARN.
additional_data_access_principals = []
