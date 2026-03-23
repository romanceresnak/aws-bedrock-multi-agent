# ─────────────────────────────────────────────────────────────
# OpenSearch Serverless — Vector store for Bedrock Knowledge Base
# ─────────────────────────────────────────────────────────────

resource "aws_opensearchserverless_security_policy" "kb_encryption" {
  name        = "${local.name_prefix}-enc"
  type        = "encryption"
  description = "Encryption policy for KB collection"

  policy = jsonencode({
    Rules = [
      {
        ResourceType = "collection"
        Resource     = ["collection/${local.name_prefix}-kb"]
      }
    ]
    AWSOwnedKey = true
  })
}

resource "aws_opensearchserverless_security_policy" "kb_network" {
  name        = "${local.name_prefix}-net"
  type        = "network"
  description = "Network policy — public access for Bedrock service"

  policy = jsonencode([
    {
      Description = "Public access for Bedrock Knowledge Base"
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${local.name_prefix}-kb"]
        },
        {
          ResourceType = "dashboard"
          Resource     = ["collection/${local.name_prefix}-kb"]
        }
      ]
      AllowFromPublic = true
    }
  ])
}

resource "aws_opensearchserverless_access_policy" "kb_data" {
  name        = "${local.name_prefix}-data"
  type        = "data"
  description = "Data access for Bedrock KB role and Lambda"

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "index"
          Resource     = ["index/${local.name_prefix}-kb/*", "index/${local.name_prefix}-kb/bedrock-knowledge-base-index"]
          Permission = [
            "aoss:CreateIndex",
            "aoss:DeleteIndex",
            "aoss:UpdateIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument",
          ]
        },
        {
          ResourceType = "collection"
          Resource     = ["collection/${local.name_prefix}-kb"]
          Permission = [
            "aoss:CreateCollectionItems",
            "aoss:DeleteCollectionItems",
            "aoss:UpdateCollectionItems",
            "aoss:DescribeCollectionItems",
          ]
        }
      ]
      Principal = [
        aws_iam_role.bedrock_kb.arn,
        aws_iam_role.bedrock_agent.arn,
        "arn:aws:iam::255834079310:user/iam-roman-cli",
      ]
    }
  ])
}

# Collection — must be created AFTER policies
resource "aws_opensearchserverless_collection" "kb" {
  name        = "${local.name_prefix}-kb"
  type        = "VECTORSEARCH"
  description = "Vector store for Bedrock Knowledge Base"

  depends_on = [
    aws_opensearchserverless_security_policy.kb_encryption,
    aws_opensearchserverless_security_policy.kb_network,
    aws_opensearchserverless_access_policy.kb_data,
  ]
}

# NOTE: The vector index itself must be created via the OpenSearch API or
# the AWS Console after the collection is ACTIVE. Bedrock will also create
# it automatically when you run scripts/01_create_knowledge_base.py.
# The index name must be: bedrock-knowledge-base-index
