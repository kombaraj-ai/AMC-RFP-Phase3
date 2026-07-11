# Handoff to the app-code follow-on task: these map roughly 1:1 onto new
# fields the DEV .env.dev-style Settings class will need once the data
# layer swaps from SQLite/Chroma to DynamoDB/OpenSearch (see
# infra/terraform/README.md's "settings mapping" section).

output "dynamodb_table_name" {
  value = module.dynamodb.table_name
}

output "opensearch_collection_endpoint" {
  value = module.opensearch_serverless.collection_endpoint
}

output "opensearch_collection_arn" {
  value = module.opensearch_serverless.collection_arn
}

output "kb_docs_bucket_name" {
  value = module.s3_kb_docs.bucket_name
}

output "ecr_repository_url" {
  value = module.ecr.repository_url
}

output "gateway_url" {
  value = module.agentcore_gateway.gateway_url
}

output "memory_id" {
  value = module.agentcore_memory.memory_id
}

output "knowledge_base_id" {
  value = var.enable_knowledge_base ? module.knowledge_base[0].knowledge_base_id : null
}

output "agent_runtime_arn" {
  value = var.enable_agent_runtime ? module.agentcore_runtime[0].agent_runtime_arn : null
}

output "runtime_role_arn" {
  value = module.iam.runtime_role_arn
}
