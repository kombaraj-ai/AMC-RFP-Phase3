output "knowledge_base_id" {
  value = aws_bedrockagent_knowledge_base.fund_commentary.id
}

output "knowledge_base_arn" {
  value = aws_bedrockagent_knowledge_base.fund_commentary.arn
}

output "data_source_id" {
  value = aws_bedrockagent_data_source.fund_commentary_docs.data_source_id
}

output "embedding_model_arn" {
  value = local.embedding_model_arn
}
