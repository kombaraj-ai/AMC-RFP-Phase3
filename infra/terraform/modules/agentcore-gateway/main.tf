# AWS_IAM auth (SigV4) per the auth-model decision - internal tool, no
# external end users calling the Gateway directly, so no Cognito/JWT infra.
resource "aws_bedrockagentcore_gateway" "amc_tools" {
  name            = "${var.name_prefix}-amc-gateway"
  role_arn        = var.gateway_role_arn
  authorizer_type = "AWS_IAM"
  protocol_type   = "MCP"
  kms_key_arn     = var.kms_key_arn
  description     = "Exposes AMC quant/qual tools as MCP tools for the agent runtime"

  tags = var.tags
}

resource "aws_bedrockagentcore_gateway_target" "lambda_tool" {
  for_each = var.lambda_tools

  name               = "${var.name_prefix}-${each.key}"
  gateway_identifier = aws_bedrockagentcore_gateway.amc_tools.gateway_id
  description        = each.value.description

  credential_provider_configuration {
    gateway_iam_role {}
  }

  target_configuration {
    mcp {
      lambda {
        lambda_arn = each.value.lambda_arn

        tool_schema {
          inline_payload {
            name        = each.key
            description = each.value.description

            input_schema {
              type        = "object"
              description = "Placeholder input schema - replace with the real per-tool schema in the app-code follow-on task."

              property {
                name        = "query"
                type        = "string"
                description = "Freeform request for the ${each.key} tool"
                required    = true
              }
            }

            output_schema {
              type = "object"

              property {
                name     = "status"
                type     = "string"
                required = true
              }

              property {
                name = "result"
                type = "string"
              }
            }
          }
        }
      }
    }
  }
}
