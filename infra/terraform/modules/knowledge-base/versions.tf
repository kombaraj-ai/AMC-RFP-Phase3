terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.27.0, < 7.0.0" # s3_vectors_configuration in aws_bedrockagent_knowledge_base landed in 6.27.0
    }
  }
}
