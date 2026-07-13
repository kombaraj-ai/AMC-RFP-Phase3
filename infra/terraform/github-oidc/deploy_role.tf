# --- deploy_role ---------------------------------------------------------
# One role per environment, assumed only by deploy.yml's jobs (which is
# workflow_dispatch-only - see .github/workflows/deploy.yml). Trust
# condition matches `sub = "...:environment:<env>"` exactly. GitHub only
# ever mints a token with an `environment:` claim for a job that explicitly
# declares `environment: <env>` in its YAML - a pull_request-triggered job
# never carries this claim (see plan_role.tf). This means even a
# misconfigured workflow can't get a PR run to assume a deploy role - the
# trust policy itself refuses it, independent of workflow logic or whatever
# GitHub Environment protection-rule settings happen to be configured.
#
# Permissions are scoped by resource-name-prefix ("${var.project}-<env>-*")
# everywhere the target service's ARN format supports it, following the
# exact precedent already established in
# modules/iam/lambda_execution_role.tf's CloudWatchLogsOwnFunctions
# statement - this is what keeps dev/staging/prod isolated from each other
# despite sharing one AWS account (see the project's own "Locked-in
# architecture decisions": isolation is by naming convention + separate
# Terraform state, not separate accounts - a deploy role that ignored this
# convention would quietly undermine that isolation for CI).
#
# A handful of actions are AWS-imposed exceptions that require
# `resources = ["*"]` regardless of scoping intent (ecr:GetAuthorizationToken,
# most OpenSearch Serverless control-plane actions, kms:CreateKey,
# Lambda event-source-mapping actions) - each is called out inline so it
# doesn't read as an oversight. A few S3 Vectors / AgentCore action names
# are best-effort against AWS's published docs and not yet independently
# verified by a real apply - flagged the same way this project already
# flags similar uncertainty elsewhere (see knowledge_base_role.tf's
# S3VectorsDataPlane comment, which documents a real wrong-action-name
# incident found only via a live AccessDenied). Expect to add a missing
# action here if a real `terraform apply` through this role surfaces one.

locals {
  environments = ["dev", "staging", "prod"]
}

data "aws_iam_policy_document" "deploy_trust" {
  for_each = toset(local.environments)

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repo}:environment:${each.key}"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  for_each = toset(local.environments)

  name               = "${var.project}-${each.key}-gha-deploy-role"
  assume_role_policy = data.aws_iam_policy_document.deploy_trust[each.key].json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "deploy_permissions" {
  for_each = toset(local.environments)

  statement {
    sid    = "IamRolesAndInlinePolicies"
    effect = "Allow"
    actions = [
      "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:UpdateRole",
      "iam:UpdateAssumeRolePolicy", "iam:TagRole", "iam:UntagRole", "iam:ListRoleTags",
      "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy", "iam:ListRolePolicies",
      "iam:ListInstanceProfilesForRole", "iam:ListAttachedRolePolicies",
      "iam:AttachRolePolicy", "iam:DetachRolePolicy",
    ]
    resources = ["arn:aws:iam::${local.account_id}:role/${var.project}-${each.key}-*"]
  }

  statement {
    sid       = "IamPassRoleForOwnServiceRoles"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${local.account_id}:role/${var.project}-${each.key}-*"]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values = [
        "lambda.amazonaws.com",
        "bedrock.amazonaws.com",
        "bedrock-agentcore.amazonaws.com",
      ]
    }
  }

  statement {
    sid       = "IamReadOidcProvider"
    effect    = "Allow"
    actions   = ["iam:GetOpenIDConnectProvider"]
    resources = [aws_iam_openid_connect_provider.github_actions.arn]
  }

  statement {
    sid    = "Ecr"
    effect = "Allow"
    actions = [
      "ecr:CreateRepository", "ecr:DeleteRepository", "ecr:DescribeRepositories",
      "ecr:PutLifecyclePolicy", "ecr:GetLifecyclePolicy", "ecr:DeleteLifecyclePolicy",
      "ecr:PutImageScanningConfiguration", "ecr:TagResource", "ecr:UntagResource",
      "ecr:ListTagsForResource", "ecr:DescribeImages", "ecr:BatchGetImage", "ecr:PutImage",
      "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload",
      "ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer",
      "ecr:SetRepositoryPolicy", "ecr:GetRepositoryPolicy", "ecr:DeleteRepositoryPolicy",
    ]
    resources = ["arn:aws:ecr:${var.aws_region}:${local.account_id}:repository/${var.project}-${each.key}-*"]
  }

  statement {
    sid       = "EcrAuth"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # AWS-imposed - this action has no resource-level scoping.
  }

  # deploy.yml's `promote` job crane-copies an image FROM dev's ECR repo INTO
  # this environment's own repo - the one deliberate crack in the
  # per-environment isolation convention above, required for build-once/
  # promote (see .github/workflows/deploy.yml). Read-only, and scoped to the
  # specific dev repo ARN, never wildcarded. dev's own role does not need
  # this statement at all (it only ever pushes to its own repo).
  dynamic "statement" {
    for_each = each.key == "dev" ? [] : [1]
    content {
      sid    = "CrossEnvReadDevEcrForPromotion"
      effect = "Allow"
      actions = [
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchCheckLayerAvailability",
      ]
      resources = ["arn:aws:ecr:${var.aws_region}:${local.account_id}:repository/${var.project}-dev-agent-runtime"]
    }
  }

  statement {
    sid    = "DynamoDb"
    effect = "Allow"
    actions = [
      "dynamodb:CreateTable", "dynamodb:DeleteTable", "dynamodb:DescribeTable", "dynamodb:UpdateTable",
      "dynamodb:UpdateContinuousBackups", "dynamodb:DescribeContinuousBackups",
      "dynamodb:DescribeTimeToLive", "dynamodb:UpdateTimeToLive",
      "dynamodb:TagResource", "dynamodb:UntagResource", "dynamodb:ListTagsOfResource",
    ]
    resources = ["arn:aws:dynamodb:${var.aws_region}:${local.account_id}:table/${var.project}-${each.key}-*"]
  }

  statement {
    sid    = "S3ProjectBuckets"
    effect = "Allow"
    actions = [
      "s3:CreateBucket", "s3:DeleteBucket", "s3:GetBucketLocation", "s3:GetBucketAcl", "s3:PutBucketAcl",
      "s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:DeleteObjectVersion",
      "s3:ListBucket", "s3:ListBucketVersions",
      "s3:GetLifecycleConfiguration", "s3:PutLifecycleConfiguration",
      "s3:GetEncryptionConfiguration", "s3:PutEncryptionConfiguration",
      "s3:GetBucketNotification", "s3:PutBucketNotification",
      "s3:GetBucketPublicAccessBlock", "s3:PutBucketPublicAccessBlock",
      "s3:GetBucketPolicy", "s3:PutBucketPolicy", "s3:DeleteBucketPolicy",
      "s3:GetBucketVersioning", "s3:PutBucketVersioning",
      "s3:GetBucketTagging", "s3:PutBucketTagging",
      "s3:ForceDeleteBucket",
    ]
    resources = [
      "arn:aws:s3:::${var.project}-${each.key}-*",
      "arn:aws:s3:::${var.project}-${each.key}-*/*",
    ]
  }

  # Own environment's slice of the shared Terraform state bucket, scoped by
  # object-key prefix rather than the whole bucket - matches backend.hcl's
  # `key = "<env>/terraform.tfstate"` convention used everywhere else.
  statement {
    sid       = "S3StateBucketOwnEnvironment"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::${var.state_bucket_name}/${each.key}/*"]
  }

  statement {
    sid       = "S3StateBucketListOwnEnvironment"
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = ["arn:aws:s3:::${var.state_bucket_name}"]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${each.key}/*"]
    }
  }

  # OpenSearch Serverless control plane (collection + security/access
  # policies). Most aoss control-plane actions don't support resource-level
  # ARN scoping at all (per AWS's own Service Authorization Reference for
  # aoss) - Resource = "*" here is an AWS-imposed constraint, not a scoping
  # choice. AOSS *data-plane* access (actually reading/writing vectors) is
  # controlled separately by the collection's own access policy, not by this
  # IAM policy - see the additional_data_access_principals tfvars change
  # this role's ARN also needs (infra/terraform/README.md's pass-2 section).
  statement {
    sid    = "OpenSearchServerlessControlPlane"
    effect = "Allow"
    actions = [
      "aoss:CreateCollection", "aoss:DeleteCollection", "aoss:UpdateCollection", "aoss:BatchGetCollection",
      "aoss:CreateSecurityPolicy", "aoss:UpdateSecurityPolicy", "aoss:GetSecurityPolicy",
      "aoss:DeleteSecurityPolicy", "aoss:ListSecurityPolicies",
      "aoss:CreateAccessPolicy", "aoss:UpdateAccessPolicy", "aoss:GetAccessPolicy",
      "aoss:DeleteAccessPolicy", "aoss:ListAccessPolicies",
      "aoss:TagResource", "aoss:UntagResource", "aoss:ListTagsForResource",
    ]
    resources = ["*"]
  }

  # S3 Vectors control plane (dev-only backend today - see
  # environments/dev/variables.tf's vector_store_backend - scoped
  # identically for all three environments in case staging/prod ever opt
  # in). Data-plane action names are confirmed correct
  # (knowledge_base_role.tf's S3VectorsDataPlane comment documents the real
  # incident that found them); these control-plane names follow the same
  # AWS doc but are not yet independently verified against a live apply.
  statement {
    sid    = "S3VectorsControlPlane"
    effect = "Allow"
    actions = [
      "s3vectors:CreateVectorBucket", "s3vectors:DeleteVectorBucket", "s3vectors:GetVectorBucket",
      "s3vectors:PutVectorBucketPolicy", "s3vectors:GetVectorBucketPolicy", "s3vectors:DeleteVectorBucketPolicy",
      "s3vectors:CreateIndex", "s3vectors:DeleteIndex", "s3vectors:GetIndex", "s3vectors:ListIndexes",
      "s3vectors:TagResource", "s3vectors:UntagResource", "s3vectors:ListTagsForResource",
    ]
    resources = [
      "arn:aws:s3vectors:${var.aws_region}:${local.account_id}:bucket/${var.project}-${each.key}-*",
      "arn:aws:s3vectors:${var.aws_region}:${local.account_id}:bucket/${var.project}-${each.key}-*/index/*",
    ]
  }

  # Bedrock Knowledge Base. IDs are AWS-assigned, not name-prefixable like
  # ECR/DynamoDB/S3, so scoped to region/account rather than a resource-name
  # prefix - still meaningfully narrower than "*".
  statement {
    sid    = "BedrockKnowledgeBase"
    effect = "Allow"
    actions = [
      "bedrock:CreateKnowledgeBase", "bedrock:DeleteKnowledgeBase", "bedrock:GetKnowledgeBase", "bedrock:UpdateKnowledgeBase",
      "bedrock:CreateDataSource", "bedrock:DeleteDataSource", "bedrock:GetDataSource", "bedrock:UpdateDataSource",
      "bedrock:StartIngestionJob", "bedrock:GetIngestionJob", "bedrock:ListIngestionJobs",
      "bedrock:TagResource", "bedrock:UntagResource", "bedrock:ListTagsForResource",
    ]
    resources = ["arn:aws:bedrock:${var.aws_region}:${local.account_id}:knowledge-base/*"]
  }

  statement {
    sid       = "BedrockFoundationModelReadOnly"
    effect    = "Allow"
    actions   = ["bedrock:GetFoundationModel", "bedrock:ListFoundationModels"]
    resources = ["*"] # AWS-owned foundation models, not this account's resources.
  }

  # AgentCore Runtime/Gateway/Memory. AWS appends a random suffix to each
  # resource's ID (e.g. this project's real runtime ARN ends in
  # "-X1c5y89vze"), so these can't be name-prefix-scoped the way
  # ECR/DynamoDB/S3 are - scoped to resource-type/region/account instead.
  statement {
    sid    = "AgentCoreRuntimeGatewayMemory"
    effect = "Allow"
    actions = [
      "bedrock-agentcore:CreateAgentRuntime", "bedrock-agentcore:DeleteAgentRuntime",
      "bedrock-agentcore:GetAgentRuntime", "bedrock-agentcore:UpdateAgentRuntime", "bedrock-agentcore:ListAgentRuntimes",
      "bedrock-agentcore:CreateGateway", "bedrock-agentcore:DeleteGateway",
      "bedrock-agentcore:GetGateway", "bedrock-agentcore:UpdateGateway",
      "bedrock-agentcore:CreateGatewayTarget", "bedrock-agentcore:DeleteGatewayTarget",
      "bedrock-agentcore:GetGatewayTarget", "bedrock-agentcore:UpdateGatewayTarget", "bedrock-agentcore:ListGatewayTargets",
      "bedrock-agentcore:CreateMemory", "bedrock-agentcore:DeleteMemory",
      "bedrock-agentcore:GetMemory", "bedrock-agentcore:UpdateMemory",
      "bedrock-agentcore:TagResource", "bedrock-agentcore:UntagResource", "bedrock-agentcore:ListTagsForResource",
    ]
    resources = [
      "arn:aws:bedrock-agentcore:${var.aws_region}:${local.account_id}:runtime/*",
      "arn:aws:bedrock-agentcore:${var.aws_region}:${local.account_id}:gateway/*",
      "arn:aws:bedrock-agentcore:${var.aws_region}:${local.account_id}:memory/*",
    ]
  }

  statement {
    sid    = "Lambda"
    effect = "Allow"
    actions = [
      "lambda:CreateFunction", "lambda:DeleteFunction", "lambda:GetFunction", "lambda:GetFunctionConfiguration",
      "lambda:UpdateFunctionCode", "lambda:UpdateFunctionConfiguration",
      "lambda:AddPermission", "lambda:RemovePermission", "lambda:GetPolicy",
      "lambda:TagResource", "lambda:UntagResource", "lambda:ListTags",
    ]
    resources = ["arn:aws:lambda:${var.aws_region}:${local.account_id}:function:${var.project}-${each.key}-*"]
  }

  # Event source mappings (SQS -> Lambda, kb-ingestion-sync) are identified
  # by an AWS-generated UUID, not the function name, so can't be
  # name-prefix-scoped - Resource = "*" here is an ARN-format constraint,
  # not a scoping choice.
  statement {
    sid    = "LambdaEventSourceMappings"
    effect = "Allow"
    actions = [
      "lambda:CreateEventSourceMapping", "lambda:DeleteEventSourceMapping",
      "lambda:GetEventSourceMapping", "lambda:UpdateEventSourceMapping", "lambda:ListEventSourceMappings",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "Sqs"
    effect = "Allow"
    actions = [
      "sqs:CreateQueue", "sqs:DeleteQueue", "sqs:GetQueueAttributes", "sqs:SetQueueAttributes", "sqs:GetQueueUrl",
      "sqs:TagQueue", "sqs:UntagQueue", "sqs:ListQueueTags",
    ]
    resources = ["arn:aws:sqs:${var.aws_region}:${local.account_id}:${var.project}-${each.key}-*"]
  }

  statement {
    sid    = "CloudWatchLogGroups"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup", "logs:DeleteLogGroup", "logs:PutRetentionPolicy", "logs:DescribeLogGroups",
      "logs:TagResource", "logs:UntagResource", "logs:ListTagsForResource",
      "logs:TagLogGroup", "logs:UntagLogGroup", # legacy-API equivalents some provider versions still call
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:/aws/lambda/${var.project}-${each.key}-*",
      "arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:/amc-orchestrator/${var.project}-${each.key}/*",
    ]
  }

  statement {
    sid    = "CloudWatchDashboardAndAlarms"
    effect = "Allow"
    actions = [
      "cloudwatch:PutDashboard", "cloudwatch:DeleteDashboards", "cloudwatch:GetDashboard",
      "cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms", "cloudwatch:DescribeAlarms",
      "cloudwatch:TagResource", "cloudwatch:UntagResource", "cloudwatch:ListTagsForResource",
    ]
    resources = [
      "arn:aws:cloudwatch::${local.account_id}:dashboard/${var.project}-${each.key}-*",
      "arn:aws:cloudwatch:${var.aws_region}:${local.account_id}:alarm:${var.project}-${each.key}-*",
    ]
  }

  statement {
    sid    = "Sns"
    effect = "Allow"
    actions = [
      "sns:CreateTopic", "sns:DeleteTopic", "sns:GetTopicAttributes", "sns:SetTopicAttributes",
      "sns:Subscribe", "sns:Unsubscribe", "sns:ListSubscriptionsByTopic",
      "sns:TagResource", "sns:UntagResource", "sns:ListTagsForResource",
    ]
    resources = ["arn:aws:sns:${var.aws_region}:${local.account_id}:${var.project}-${each.key}-*"]
  }

  # KMS CMKs - only actually created when this environment's use_cmk = true
  # (staging/prod, see environments/*/terraform.tfvars). kms:CreateKey has
  # no resource to scope to before the key exists, an AWS-imposed
  # constraint; the alias IS name-prefixable and scoped accordingly.
  statement {
    sid       = "KmsCreateKey"
    effect    = "Allow"
    actions   = ["kms:CreateKey"]
    resources = ["*"]
  }

  statement {
    sid    = "KmsManageOwnKeys"
    effect = "Allow"
    actions = [
      "kms:DescribeKey", "kms:EnableKeyRotation", "kms:PutKeyPolicy", "kms:ScheduleKeyDeletion",
      "kms:TagResource", "kms:UntagResource", "kms:ListResourceTags",
      "kms:CreateAlias", "kms:DeleteAlias", "kms:UpdateAlias",
    ]
    resources = [
      "arn:aws:kms:${var.aws_region}:${local.account_id}:key/*",
      "arn:aws:kms:${var.aws_region}:${local.account_id}:alias/${var.project}-${each.key}-*",
    ]
  }
}

resource "aws_iam_role_policy" "deploy" {
  for_each = toset(local.environments)

  name   = "${var.project}-${each.key}-gha-deploy-policy"
  role   = aws_iam_role.deploy[each.key].id
  policy = data.aws_iam_policy_document.deploy_permissions[each.key].json
}
