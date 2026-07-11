terraform {
  required_providers {
    opensearch = {
      source                = "opensearch-project/opensearch"
      version               = ">= 2.3.2, < 3.0.0"
      configuration_aliases = [opensearch]
    }
  }
}
