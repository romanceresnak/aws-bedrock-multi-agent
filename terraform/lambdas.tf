# ─────────────────────────────────────────────────────────────
# Lambda: Query Rewrite
# ─────────────────────────────────────────────────────────────

data "archive_file" "query_rewrite" {
  type        = "zip"
  source_file = "${path.module}/../lambda/query_rewrite/handler.py"
  output_path = "${path.module}/../lambda/query_rewrite/function.zip"
}

resource "aws_lambda_function" "query_rewrite" {
  function_name    = "${local.name_prefix}-query-rewrite"
  description      = "Rewrites user queries for better retrieval using Claude Haiku"
  role             = aws_iam_role.lambda_exec.arn
  runtime          = var.lambda_runtime
  handler          = "handler.handler"
  filename         = data.archive_file.query_rewrite.output_path
  source_code_hash = data.archive_file.query_rewrite.output_base64sha256
  timeout          = 60
  memory_size      = var.lambda_memory_mb

  environment {
    variables = {
      AWS_REGION_OVERRIDE = var.aws_region
    }
  }
}

resource "aws_cloudwatch_log_group" "query_rewrite" {
  name              = "/aws/lambda/${aws_lambda_function.query_rewrite.function_name}"
  retention_in_days = 14
}


# ─────────────────────────────────────────────────────────────
# Lambda: Grader
# ─────────────────────────────────────────────────────────────

data "archive_file" "grader" {
  type        = "zip"
  source_file = "${path.module}/../lambda/grader/handler.py"
  output_path = "${path.module}/../lambda/grader/function.zip"
}

resource "aws_lambda_function" "grader" {
  function_name    = "${local.name_prefix}-grader"
  description      = "Structured quality evaluation of agent responses"
  role             = aws_iam_role.lambda_exec.arn
  runtime          = var.lambda_runtime
  handler          = "handler.handler"
  filename         = data.archive_file.grader.output_path
  source_code_hash = data.archive_file.grader.output_base64sha256
  timeout          = 60
  memory_size      = var.lambda_memory_mb

  environment {
    variables = {
      AWS_REGION_OVERRIDE = var.aws_region
    }
  }
}

resource "aws_cloudwatch_log_group" "grader" {
  name              = "/aws/lambda/${aws_lambda_function.grader.function_name}"
  retention_in_days = 14
}


# ─────────────────────────────────────────────────────────────
# Lambda: Image Generation Action Group
# ─────────────────────────────────────────────────────────────

data "archive_file" "image_action" {
  type        = "zip"
  source_file = "${path.module}/../lambda/image_generation_action/handler.py"
  output_path = "${path.module}/../lambda/image_generation_action/function.zip"
}

resource "aws_lambda_function" "image_action" {
  function_name    = "${local.name_prefix}-image-action"
  description      = "Bedrock Action Group — Titan Image Generator v2"
  role             = aws_iam_role.lambda_exec.arn
  runtime          = var.lambda_runtime
  handler          = "handler.handler"
  filename         = data.archive_file.image_action.output_path
  source_code_hash = data.archive_file.image_action.output_base64sha256
  timeout          = var.lambda_timeout
  memory_size      = 512  # Image processing needs more memory

  environment {
    variables = {
      AWS_REGION_OVERRIDE     = var.aws_region
      S3_IMAGES_BUCKET        = aws_s3_bucket.images.id
      PRESIGNED_URL_EXPIRY    = tostring(var.image_presigned_url_expiry)
    }
  }
}

resource "aws_cloudwatch_log_group" "image_action" {
  name              = "/aws/lambda/${aws_lambda_function.image_action.function_name}"
  retention_in_days = 14
}


# ─────────────────────────────────────────────────────────────
# Lambda: Orchestrator (API Gateway entry point)
# ─────────────────────────────────────────────────────────────

data "archive_file" "orchestrator" {
  type        = "zip"
  source_file = "${path.module}/../lambda/orchestrator/handler.py"
  output_path = "${path.module}/../lambda/orchestrator/function.zip"
}

resource "aws_lambda_function" "orchestrator" {
  function_name    = "${local.name_prefix}-orchestrator"
  description      = "Top-level orchestrator: rewrite → supervisor → grade → A2I"
  role             = aws_iam_role.lambda_exec.arn
  runtime          = var.lambda_runtime
  handler          = "handler.handler"
  filename         = data.archive_file.orchestrator.output_path
  source_code_hash = data.archive_file.orchestrator.output_base64sha256
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory_mb

  environment {
    variables = {
      AWS_REGION_OVERRIDE        = var.aws_region
      QUERY_REWRITE_LAMBDA_ARN   = aws_lambda_function.query_rewrite.arn
      GRADER_LAMBDA_ARN          = aws_lambda_function.grader.arn
      # Set after running scripts/03_create_supervisor.py:
      SUPERVISOR_AGENT_ID        = ""
      SUPERVISOR_ALIAS_ID        = ""
      # Set after creating A2I flow in Console:
      A2I_FLOW_ARN               = ""
    }
  }

  lifecycle {
    ignore_changes = [
      # These are populated after Bedrock resources are created via scripts
      environment
    ]
  }
}

resource "aws_cloudwatch_log_group" "orchestrator" {
  name              = "/aws/lambda/${aws_lambda_function.orchestrator.function_name}"
  retention_in_days = 14
}


# ─────────────────────────────────────────────────────────────
# API Gateway (HTTP API) → Orchestrator Lambda
# ─────────────────────────────────────────────────────────────

resource "aws_apigatewayv2_api" "main" {
  name          = "${local.name_prefix}-api"
  protocol_type = "HTTP"
  description   = "Multi-Agent Bedrock API"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["POST", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_integration" "orchestrator" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.orchestrator.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "query" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /query"
  target    = "integrations/${aws_apigatewayv2_integration.orchestrator.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.orchestrator.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

output "api_endpoint" {
  description = "API Gateway endpoint — POST /query to invoke the pipeline"
  value       = "${aws_apigatewayv2_stage.default.invoke_url}/query"
}


# ─────────────────────────────────────────────────────────────
# Lambda: Invoke RAG Agent (Action Group for Supervisor)
# ─────────────────────────────────────────────────────────────

data "archive_file" "invoke_rag_agent" {
  type        = "zip"
  source_file = "${path.module}/../lambda/invoke_rag_agent/handler.py"
  output_path = "${path.module}/../lambda/invoke_rag_agent/function.zip"
}

resource "aws_lambda_function" "invoke_rag_agent" {
  function_name    = "${local.name_prefix}-invoke-rag-agent"
  description      = "Action Group — Invokes RAG agent for document search"
  role             = aws_iam_role.lambda_exec.arn
  runtime          = var.lambda_runtime
  handler          = "handler.handler"
  filename         = data.archive_file.invoke_rag_agent.output_path
  source_code_hash = data.archive_file.invoke_rag_agent.output_base64sha256
  timeout          = 60
  memory_size      = var.lambda_memory_mb

  environment {
    variables = {
      AWS_REGION_OVERRIDE = var.aws_region
      RAG_AGENT_ID        = ""
      RAG_ALIAS_ID        = ""
    }
  }

  lifecycle {
    ignore_changes = [
      environment
    ]
  }
}

resource "aws_cloudwatch_log_group" "invoke_rag_agent" {
  name              = "/aws/lambda/${aws_lambda_function.invoke_rag_agent.function_name}"
  retention_in_days = 14
}

resource "aws_lambda_permission" "bedrock_invoke_rag_agent" {
  statement_id  = "AllowBedrockAgentInvokeRAG"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.invoke_rag_agent.function_name
  principal     = "bedrock.amazonaws.com"
  source_account = data.aws_caller_identity.current.account_id
}

output "invoke_rag_agent_arn" {
  description = "ARN of Lambda function that invokes RAG agent"
  value       = aws_lambda_function.invoke_rag_agent.arn
}
