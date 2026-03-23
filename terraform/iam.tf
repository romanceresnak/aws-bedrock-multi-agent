# ─────────────────────────────────────────────────────────────
# IAM Role: Bedrock Agents (Supervisor + Sub-Agents)
# ─────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "bedrock_agent_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "bedrock_agent" {
  name               = "${local.name_prefix}-agent-role"
  assume_role_policy = data.aws_iam_policy_document.bedrock_agent_trust.json
}

resource "aws_iam_role_policy" "bedrock_agent_inline" {
  name = "bedrock-agent-permissions"
  role = aws_iam_role.bedrock_agent.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockInvokeModels"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:GetFoundationModel",
        ]
        Resource = [
          "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.claude-3-haiku*",
          "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.claude-3-sonnet*",
          "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.claude-3-5-sonnet*",
          "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-image-generator*",
          "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text*",
        ]
      },
      {
        Sid    = "BedrockAgentOperations"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeAgent",
          "bedrock:RetrieveAndGenerate",
          "bedrock:Retrieve",
        ]
        Resource = "*"
      },
      {
        Sid    = "S3DocumentAccess"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.docs.arn,
          "${aws_s3_bucket.docs.arn}/*",
        ]
      },
      {
        Sid    = "S3ImageWrite"
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject"]
        Resource = [
          aws_s3_bucket.images.arn,
          "${aws_s3_bucket.images.arn}/*",
        ]
      },
      {
        Sid      = "OpenSearchAccess"
        Effect   = "Allow"
        Action   = ["aoss:APIAccessAll"]
        Resource = aws_opensearchserverless_collection.kb.arn
      },
      {
        Sid    = "LambdaInvoke"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          aws_lambda_function.image_action.arn,
        ]
      },
      {
        Sid    = "A2ISubmit"
        Effect = "Allow"
        Action = ["sagemaker:StartHumanLoop", "sagemaker:DescribeHumanLoop"]
        Resource = "*"
      },
    ]
  })
}


# ─────────────────────────────────────────────────────────────
# IAM Role: Bedrock Knowledge Base
# ─────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "bedrock_kb_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "bedrock_kb" {
  name               = "${local.name_prefix}-kb-role"
  assume_role_policy = data.aws_iam_policy_document.bedrock_kb_trust.json
}

resource "aws_iam_role_policy" "bedrock_kb_inline" {
  name = "bedrock-kb-permissions"
  role = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3ReadDocs"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.docs.arn,
          "${aws_s3_bucket.docs.arn}/*",
        ]
      },
      {
        Sid    = "EmbeddingModel"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0"
        ]
      },
      {
        Sid      = "OpenSearchWrite"
        Effect   = "Allow"
        Action   = ["aoss:APIAccessAll"]
        Resource = aws_opensearchserverless_collection.kb.arn
      },
    ]
  })
}


# ─────────────────────────────────────────────────────────────
# IAM Role: Lambda Execution
# ─────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${local.name_prefix}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_inline" {
  name = "lambda-bedrock-permissions"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockInvoke"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeAgent",
        ]
        Resource = "*"
      },
      {
        Sid    = "S3ImagesWrite"
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject", "s3:GeneratePresignedUrl"]
        Resource = [
          aws_s3_bucket.images.arn,
          "${aws_s3_bucket.images.arn}/*",
        ]
      },
      {
        Sid    = "LambdaInvokePeers"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          "arn:aws:lambda:${var.aws_region}:${local.account_id}:function:${local.name_prefix}-*"
        ]
      },
      {
        Sid    = "A2ISubmit"
        Effect = "Allow"
        Action = ["sagemaker:StartHumanLoop", "sagemaker:DescribeHumanLoop"]
        Resource = "*"
      },
    ]
  })
}


# ─────────────────────────────────────────────────────────────
# Lambda Resource-Based Policy: allow Bedrock Agent to invoke image action Lambda
# ─────────────────────────────────────────────────────────────

resource "aws_lambda_permission" "bedrock_invoke_image_action" {
  statement_id  = "AllowBedrockAgentInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.image_action.function_name
  principal     = "bedrock.amazonaws.com"
  source_arn    = "arn:aws:bedrock:${var.aws_region}:${local.account_id}:agent/*"
}
