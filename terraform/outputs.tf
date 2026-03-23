output "docs_bucket_name" {
  description = "S3 bucket name for source documents"
  value       = aws_s3_bucket.docs.id
}

output "docs_bucket_arn" {
  description = "S3 bucket ARN for source documents"
  value       = aws_s3_bucket.docs.arn
}

output "images_bucket_name" {
  description = "S3 bucket name for generated images"
  value       = aws_s3_bucket.images.id
}

output "images_bucket_arn" {
  description = "S3 bucket ARN for generated images"
  value       = aws_s3_bucket.images.arn
}

output "opensearch_collection_arn" {
  description = "OpenSearch Serverless collection ARN"
  value       = aws_opensearchserverless_collection.kb.arn
}

output "opensearch_collection_endpoint" {
  description = "OpenSearch Serverless collection endpoint"
  value       = aws_opensearchserverless_collection.kb.collection_endpoint
}

output "bedrock_agent_role_arn" {
  description = "IAM role ARN for Bedrock Agents (BEDROCK_AGENT_ROLE_ARN in .env)"
  value       = aws_iam_role.bedrock_agent.arn
}

output "kb_role_arn" {
  description = "IAM role ARN for Bedrock Knowledge Base (KB_ROLE_ARN in .env)"
  value       = aws_iam_role.bedrock_kb.arn
}

output "lambda_role_arn" {
  description = "IAM role ARN for Lambda functions (LAMBDA_ROLE_ARN in .env)"
  value       = aws_iam_role.lambda_exec.arn
}

output "query_rewrite_lambda_arn" {
  description = "ARN of the query rewrite Lambda (QUERY_REWRITE_LAMBDA_ARN in .env)"
  value       = aws_lambda_function.query_rewrite.arn
}

output "grader_lambda_arn" {
  description = "ARN of the grader Lambda (GRADER_LAMBDA_ARN in .env)"
  value       = aws_lambda_function.grader.arn
}

output "image_action_lambda_arn" {
  description = "ARN of the image generation action Lambda (IMAGE_ACTION_LAMBDA_ARN in .env)"
  value       = aws_lambda_function.image_action.arn
}

output "orchestrator_lambda_arn" {
  description = "ARN of the orchestrator Lambda (ORCHESTRATOR_LAMBDA_ARN in .env)"
  value       = aws_lambda_function.orchestrator.arn
}

output "env_block" {
  description = "Ready-to-paste .env block with all Terraform-managed values"
  value       = <<-EOT
    # ── Paste into .env ─────────────────────────────
    AWS_ACCOUNT_ID=${local.account_id}
    AWS_REGION=${var.aws_region}
    BEDROCK_AGENT_ROLE_ARN=${aws_iam_role.bedrock_agent.arn}
    KB_ROLE_ARN=${aws_iam_role.bedrock_kb.arn}
    LAMBDA_ROLE_ARN=${aws_iam_role.lambda_exec.arn}
    S3_DOCS_BUCKET=${aws_s3_bucket.docs.id}
    S3_IMAGES_BUCKET=${aws_s3_bucket.images.id}
    OPENSEARCH_COLLECTION_ARN=${aws_opensearchserverless_collection.kb.arn}
    OPENSEARCH_COLLECTION_ENDPOINT=${aws_opensearchserverless_collection.kb.collection_endpoint}
    QUERY_REWRITE_LAMBDA_ARN=${aws_lambda_function.query_rewrite.arn}
    GRADER_LAMBDA_ARN=${aws_lambda_function.grader.arn}
    IMAGE_ACTION_LAMBDA_ARN=${aws_lambda_function.image_action.arn}
    ORCHESTRATOR_LAMBDA_ARN=${aws_lambda_function.orchestrator.arn}
    # ────────────────────────────────────────────────
  EOT
}
