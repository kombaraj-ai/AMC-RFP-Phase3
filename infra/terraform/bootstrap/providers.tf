provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(var.tags, {
      ManagedBy = "terraform"
      Component = "tfstate-bootstrap"
    })
  }
}
