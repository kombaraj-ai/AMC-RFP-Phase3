output "repository_url" {
  description = "e.g. 123456789012.dkr.ecr.us-east-1.amazonaws.com/amc-dev-agent-runtime - push images here, then set that tag as agentcore-runtime's image_uri variable."
  value       = aws_ecr_repository.runtime.repository_url
}

output "repository_arn" {
  value = aws_ecr_repository.runtime.arn
}

output "repository_name" {
  value = aws_ecr_repository.runtime.name
}
