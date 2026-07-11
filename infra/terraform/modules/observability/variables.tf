variable "name_prefix" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the runtime/gateway log groups. Short in dev, long in prod for audit needs."
  type        = number
  default     = 30
}

variable "dynamodb_table_name" {
  type = string
}

variable "lambda_function_names" {
  type = list(string)
}

variable "alarm_email" {
  description = "Email to subscribe to the alarm SNS topic. Empty string disables alarm notifications (the alarms/topic still exist, just nothing subscribed) - set per-env, opt-in."
  type        = string
  default     = ""
}

variable "lambda_error_alarm_threshold" {
  type    = number
  default = 5
}

variable "dynamodb_throttle_alarm_threshold" {
  type    = number
  default = 1
}

variable "tags" {
  type    = map(string)
  default = {}
}
