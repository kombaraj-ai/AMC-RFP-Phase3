"""S3-triggered Bedrock Knowledge Base ingestion sync.

Invoked by an SQS event source mapping that batches S3 ObjectCreated/
ObjectRemoved events from the KB docs bucket (see main.tf). One invocation
may represent many S3 events collapsed into a single batch - that's fine,
since a single start_ingestion_job call re-syncs the whole data source.

Terraform-owned; do not hand-edit the deployed content directly, it is
overwritten by the next `terraform apply`.
"""

import json
import os

import boto3
from botocore.exceptions import ClientError

bedrock_agent = boto3.client("bedrock-agent")

KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]
DATA_SOURCE_ID = os.environ["DATA_SOURCE_ID"]


def handler(event, context):
    try:
        response = bedrock_agent.start_ingestion_job(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            dataSourceId=DATA_SOURCE_ID,
        )
        job_id = response["ingestionJob"]["ingestionJobId"]
        return {"statusCode": 200, "body": json.dumps({"ingestionJobId": job_id})}
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConflictException":
            # A job is already running for this data source - ingestion is
            # incremental, so it will pick up whatever new/changed files
            # triggered this invocation anyway. Not a failure.
            return {"statusCode": 200, "body": json.dumps({"status": "sync_already_running"})}
        raise  # genuine failure - let SQS redrive to the DLQ
