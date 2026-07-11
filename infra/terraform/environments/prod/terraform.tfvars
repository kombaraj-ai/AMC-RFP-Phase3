aws_region  = "us-east-1"
project     = "amc-orchestrator"
environment = "prod"

# --- Phased-apply gates: leave both false on the first apply -------------
enable_knowledge_base = false
enable_agent_runtime  = false
container_image_uri   = ""

# --- Cost/HA knobs - full production posture -------------------------------
use_cmk                         = true
opensearch_standby_replicas     = "ENABLED"
dynamodb_point_in_time_recovery = true
dynamodb_deletion_protection    = true
log_retention_days              = 365
memory_event_expiry_days        = 90
ecr_untagged_image_expiry_days  = 30
ecr_max_tagged_images           = 30
alarm_email                     = "" # set to an on-call/team distribution list before go-live

# --- Model choices ----------------------------------------------------------
bedrock_model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"
embedding_model  = "titan-v2"
runtime_protocol = "HTTP"

# Add the ARN of whoever/whatever runs `terraform apply` here before the
# enable_knowledge_base=true pass, or vector-index creation will fail with
# an AOSS authorization error - see README.md. In prod this should be a
# CI/CD role, not a human's personal ARN.
additional_data_access_principals = []
