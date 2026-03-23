# Multi-Agent Orchestration on AWS — 100% Native with Amazon Bedrock

A production-ready, AWS-native multi-agent architecture using Amazon Bedrock. No LangChain, no LangGraph, no third-party orchestration — only `boto3` and managed AWS services.

## Architecture

```
User Query
    │
    ▼
Lambda (Query Rewrite)          ← Bedrock InvokeModel (Claude Haiku)
    │
    ▼
Bedrock Supervisor Agent        ← orchestrates all sub-agents
    ├── RAG Sub-Agent           ← Bedrock Agent + Knowledge Base (S3 / OpenSearch Serverless)
    ├── Search Sub-Agent        ← Bedrock Agent + Knowledge Base (S3 / HYBRID search)
    └── Image Sub-Agent         ← Bedrock Agent + Titan Image Generator v2
          │
          ▼
    Grader Lambda               ← Bedrock InvokeModel (structured eval)
          │
       Match?
      N ↙   ↘ Y
  Retry   Human-in-the-Loop     ← Amazon A2I
                │
                ▼
           Final Answer
```

## AWS Services Used

| Component | AWS Service |
|---|---|
| Orchestrator | Bedrock Supervisor Agent (Claude 3.5 Sonnet v2) |
| RAG / Search Agent | Bedrock Agent + Knowledge Base |
| Vector Store | OpenSearch Serverless |
| Embeddings | Amazon Titan Embed Text v2 |
| Image Generation | Amazon Titan Image Generator v2 |
| Grader & Query Rewrite | Lambda + Bedrock InvokeModel (Claude Haiku) |
| Human Review | Amazon A2I |
| Storage | Amazon S3 |
| Infrastructure | Terraform |

## Prerequisites

- AWS CLI configured (`aws configure`)
- Terraform ≥ 1.5
- Python ≥ 3.11
- Bedrock model access enabled in `eu-west-1` for:
  - `anthropic.claude-3-haiku-20240307-v1:0`
  - `anthropic.claude-3-sonnet-20240229-v1:0`
  - `anthropic.claude-3-5-sonnet-20241022-v2:0`
  - `amazon.titan-embed-text-v2:0`
  - `amazon.titan-image-generator-v2:0`

## Quick Start

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in AWS_ACCOUNT_ID at minimum
```

### 3. Deploy infrastructure with Terraform

```bash
cd terraform
terraform init
terraform apply
# Copy the outputs into your .env file
```

### 4. Package Lambda functions

```bash
# From project root
zip -j lambda/query_rewrite/function.zip lambda/query_rewrite/handler.py
zip -j lambda/grader/function.zip lambda/grader/handler.py
zip -j lambda/image_generation_action/function.zip lambda/image_generation_action/handler.py
zip -j lambda/orchestrator/function.zip lambda/orchestrator/handler.py
```

Then re-run `terraform apply` to push the zips.

### 5. Create Bedrock resources

Run scripts in order — each script prints the IDs it creates and appends them to `.env`:

```bash
python scripts/01_create_knowledge_base.py
python scripts/02_create_subagents.py
python scripts/03_create_supervisor.py
```

### 6. Upload documents to S3

```bash
aws s3 cp my-docs/ s3://<your-docs-bucket>/reports/ --recursive
```

Then trigger a sync ingestion:

```bash
python scripts/01_create_knowledge_base.py --sync
```

### 7. (Manual) Create A2I Flow Definition

Go to AWS Console → SageMaker → Augmented AI → Human review workflows.  
Create a new workflow, copy the ARN, and set it as `A2I_FLOW_ARN` in `.env`.

### 8. Test end-to-end

```bash
python scripts/04_test_invoke.py --query "What is our remote work policy?"
```

## Project Structure

```
multi-agent-bedrock/
├── README.md
├── requirements.txt
├── .env.example
├── lambda/
│   ├── query_rewrite/
│   │   └── handler.py          # Query rewrite via Claude Haiku
│   ├── grader/
│   │   └── handler.py          # Structured quality grader
│   ├── image_generation_action/
│   │   └── handler.py          # Titan Image Generator action group
│   └── orchestrator/
│       └── handler.py          # Top-level API Gateway entry point
├── scripts/
│   ├── 01_create_knowledge_base.py
│   ├── 02_create_subagents.py
│   ├── 03_create_supervisor.py
│   ├── 04_test_invoke.py
│   └── a2i_utils.py
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── iam.tf
│   ├── s3.tf
│   ├── opensearch.tf
│   ├── lambdas.tf
│   └── a2i.tf
└── stepfunctions/
    └── workflow.asl.json
```

## Environment Variables Reference

See `.env.example` for the full list. Key variables:

| Variable | Description |
|---|---|
| `AWS_ACCOUNT_ID` | Your 12-digit AWS account ID |
| `AWS_REGION` | Target region (default: `eu-west-1`) |
| `BEDROCK_AGENT_ROLE_ARN` | IAM role ARN for Bedrock agents |
| `KB_ROLE_ARN` | IAM role ARN for Knowledge Base |
| `S3_DOCS_BUCKET` | S3 bucket name for source documents |
| `S3_IMAGES_BUCKET` | S3 bucket name for generated images |
| `OPENSEARCH_COLLECTION_ARN` | OpenSearch Serverless collection ARN |
| `KB_ID` | Knowledge Base ID (set by script 01) |
| `RAG_AGENT_ID` / `RAG_ALIAS_ID` | RAG sub-agent IDs (set by script 02) |
| `IMAGE_AGENT_ID` / `IMAGE_ALIAS_ID` | Image sub-agent IDs (set by script 02) |
| `SUPERVISOR_AGENT_ID` / `SUPERVISOR_ALIAS_ID` | Supervisor agent IDs (set by script 03) |
| `A2I_FLOW_ARN` | A2I Flow Definition ARN (manual, from Console) |

## Cost Considerations

- **Bedrock FM tokens**: Pay-per-use. Claude Haiku is cheapest for query rewrite + grading.
- **OpenSearch Serverless**: Minimum ~$350/month for 2 OCUs. Consider this before enabling in dev.
- **Lambda**: Effectively free at this invocation volume.
- **Titan Image Generator**: ~$0.01–$0.08 per image depending on resolution/quality.
- **A2I**: Pay per human review task + reviewer cost.

Tag all resources with `Project=multi-agent-bedrock` (configured in Terraform) for Cost Explorer visibility.
