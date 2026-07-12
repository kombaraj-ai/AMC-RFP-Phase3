aws_region  = "us-east-1"
project     = "amc-orchestrator"
environment = "dev"

# --- Phased-apply gates: leave both false on the first apply -------------
enable_knowledge_base = true
enable_agent_runtime  = false
container_image_uri   = "766354255780.dkr.ecr.us-east-1.amazonaws.com/amc-orchestrator-dev-agent-runtime:v1"

# Cheapest option for dev - creates zero OpenSearch resources at all (see
# docs/architecture.md's "Dev-only vector store choice" section). Not valid
# in staging/prod (vector_store_backend is hard-locked to "opensearch" there).
vector_store_backend = "s3_vectors"

# --- Cost/HA knobs - cheapest sensible dev defaults -----------------------
use_cmk                         = false
opensearch_standby_replicas     = "DISABLED"
dynamodb_point_in_time_recovery = false
dynamodb_deletion_protection    = false
log_retention_days              = 14
memory_event_expiry_days        = 14
ecr_untagged_image_expiry_days  = 7
ecr_max_tagged_images           = 10
alarm_email                     = ""

# --- Model choices ----------------------------------------------------------
# anthropic.claude-3-5-sonnet-20241022-v2:0 reached end-of-life on Bedrock
# (confirmed live, 2026-07-12 - a real invocation returned
# ResourceNotFoundException). amazon.nova-lite-v1:0 is ACTIVE, ON_DEMAND
# (no inference-profile IAM complexity), and cheaper - confirmed sufficient
# for this project's structured-output need since Strands' BedrockModel
# only ever requests tool_choice={"any": {}} (force *some* tool use), never
# a named-tool force, and Nova supports "any" tool choice via Converse API.
bedrock_model_id = "amazon.nova-lite-v1:0"
embedding_model  = "titan-v2"
runtime_protocol = "HTTP"

# The applier's own ARN - AOSS data-plane access is gated by its own access
# policy (modules/opensearch-access-policy), not just IAM permissions;
# without this, vector-index creation fails with an AOSS authorization
# error. Confirmed via `aws sts get-caller-identity`, 2026-07-12.
additional_data_access_principals = ["arn:aws:iam::766354255780:user/eks-admin"]
