output "function_arns" {
  value = { for name, fn in aws_lambda_function.tool : name => fn.arn }
}

output "function_names" {
  value = { for name, fn in aws_lambda_function.tool : name => fn.function_name }
}
