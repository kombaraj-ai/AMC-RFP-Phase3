"""Placeholder AgentCore Gateway target handler.

Terraform-owned scaffolding only, so the Gateway + gateway_target wiring is
apply-able end-to-end in Phase 02 without depending on a not-yet-built app
container (see infra/terraform/README.md's artifact-bootstrap note). Replace
with the real quant/qual tool logic (reading TOOL_NAME / DYNAMODB_TABLE_NAME
/ OPENSEARCH_COLLECTION_ENDPOINT from the environment below) in the app-code
follow-on task - do not hand-edit this file's deployed content directly, it
is overwritten by the next `terraform apply`.
"""

import json
import os


def handler(event, context):
    tool_name = os.environ.get("TOOL_NAME", "unknown-tool")
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "status": "not_implemented",
                "tool": tool_name,
                "message": (
                    f"'{tool_name}' is a Terraform-provisioned placeholder. "
                    "Real tool logic ships in the app-code follow-on task."
                ),
            }
        ),
    }
