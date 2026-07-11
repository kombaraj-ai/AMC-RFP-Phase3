aws_region  = "us-east-1"
project     = "amc-orchestrator"
environment = "dev"

# --- Phased-apply gates: leave both false on the first apply -------------
enable_knowledge_base = false
enable_agent_runtime  = false
container_image_uri   = ""

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
bedrock_model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"
embedding_model  = "titan-v2"
runtime_protocol = "HTTP"

# Add the ARN of whoever/whatever runs `terraform apply` here before the
# enable_knowledge_base=true pass, or vector-index creation will fail with
# an AOSS authorization error - see README.md.
additional_data_access_principals = []
