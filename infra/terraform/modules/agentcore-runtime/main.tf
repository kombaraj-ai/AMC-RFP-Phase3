# network_mode = "PUBLIC" is a locked-in decision, not a default happened
# to be convenient: "VPC" mode hits a confirmed open AWS bug where the
# service-created ENIs get locked and `terraform destroy` hangs forever
# (terraform-provider-aws issue #45099, closed "not planned" - an AWS
# service-side limitation, not something a provider fix can paper over).
# See infra/terraform/README.md for the full writeup.
resource "aws_bedrockagentcore_agent_runtime" "amc_orchestrator" {
  agent_runtime_name = replace("${var.name_prefix}_agent_runtime", "-", "_")
  role_arn           = var.runtime_role_arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = var.container_image_uri
    }
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  protocol_configuration {
    server_protocol = var.protocol
  }

  environment_variables = var.environment_variables

  lifecycle_configuration {
    idle_runtime_session_timeout = var.idle_session_timeout_seconds
    max_lifetime                 = var.max_lifetime_seconds
  }

  tags = var.tags
}
