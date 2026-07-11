variable "name_prefix" {
  type = string
}

variable "image_tag_mutability" {
  description = "\"IMMUTABLE\" (recommended - a tag can never be silently repointed, forces a new tag per build) or \"MUTABLE\"."
  type        = string
  default     = "IMMUTABLE"

  validation {
    condition     = contains(["IMMUTABLE", "MUTABLE"], var.image_tag_mutability)
    error_message = "image_tag_mutability must be IMMUTABLE or MUTABLE."
  }
}

variable "untagged_image_expiry_days" {
  description = "Days after which untagged (dangling) images are expired. Tagged images are never auto-expired."
  type        = number
  default     = 14
}

variable "max_tagged_images" {
  description = "Maximum number of tagged images to retain (oldest evicted first) - bounds storage cost across many CI builds."
  type        = number
  default     = 20
}

variable "tags" {
  type    = map(string)
  default = {}
}
