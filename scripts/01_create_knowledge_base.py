"""
scripts/01_create_knowledge_base.py
────────────────────────────────────
Creates (or re-uses) a Bedrock Knowledge Base backed by S3 + OpenSearch Serverless.
Triggers an ingestion job to index documents.

Usage:
    python scripts/01_create_knowledge_base.py
    python scripts/01_create_knowledge_base.py --sync   # re-trigger ingestion only

Writes KB_ID and DATA_SOURCE_ID into your .env file.
"""

import argparse
import boto3
import json
import os
import sys
import time
import logging

from dotenv import load_dotenv, set_key

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

REGION = os.environ.get("AWS_REGION", "eu-west-1")
ACCOUNT_ID = os.environ["AWS_ACCOUNT_ID"]
KB_ROLE_ARN = os.environ["KB_ROLE_ARN"]
S3_DOCS_BUCKET = os.environ["S3_DOCS_BUCKET"]
OPENSEARCH_COLLECTION_ARN = os.environ["OPENSEARCH_COLLECTION_ARN"]

ENV_FILE = os.path.join(os.path.dirname(__file__), "..", ".env")

bedrock_agent = boto3.client("bedrock-agent", region_name=REGION)


# ─────────────────────────────────────────────────────────────
# Knowledge Base
# ─────────────────────────────────────────────────────────────

def create_knowledge_base() -> str:
    """Create a Bedrock Vector Knowledge Base using Titan Embed v2 + OpenSearch Serverless."""
    logger.info("Creating Knowledge Base...")

    response = bedrock_agent.create_knowledge_base(
        name="multi-agent-bedrock-company-docs",
        description="Company documents, policies, and internal reports",
        roleArn=KB_ROLE_ARN,
        knowledgeBaseConfiguration={
            "type": "VECTOR",
            "vectorKnowledgeBaseConfiguration": {
                "embeddingModelArn": (
                    f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0"
                )
            },
        },
        storageConfiguration={
            "type": "OPENSEARCH_SERVERLESS",
            "opensearchServerlessConfiguration": {
                "collectionArn": OPENSEARCH_COLLECTION_ARN,
                "vectorIndexName": "bedrock-knowledge-base-index",
                "fieldMapping": {
                    "vectorField": "bedrock-knowledge-base-default-vector",
                    "textField": "AMAZON_BEDROCK_TEXT_CHUNK",
                    "metadataField": "AMAZON_BEDROCK_METADATA",
                },
            },
        },
        tags={"Project": "multi-agent-bedrock"},
    )

    kb_id = response["knowledgeBase"]["knowledgeBaseId"]
    logger.info("✅ Knowledge Base created: %s", kb_id)
    return kb_id


# ─────────────────────────────────────────────────────────────
# Data Source
# ─────────────────────────────────────────────────────────────

def create_data_source(kb_id: str) -> str:
    """Attach S3 as a data source with semantic chunking."""
    logger.info("Creating S3 data source for KB %s...", kb_id)

    response = bedrock_agent.create_data_source(
        knowledgeBaseId=kb_id,
        name="s3-company-docs",
        description="Company documents from S3",
        dataSourceConfiguration={
            "type": "S3",
            "s3Configuration": {
                "bucketArn": f"arn:aws:s3:::{S3_DOCS_BUCKET}",
                "inclusionPrefixes": ["reports/", "policies/", "docs/"],
            },
        },
        vectorIngestionConfiguration={
            "chunkingConfiguration": {
                "chunkingStrategy": "SEMANTIC",
                "semanticChunkingConfiguration": {
                    "maxTokens": 300,
                    "bufferSize": 0,
                    "breakpointPercentileThreshold": 95,
                },
            }
        },
    )

    ds_id = response["dataSource"]["dataSourceId"]
    logger.info("✅ Data source created: %s", ds_id)
    return ds_id


# ─────────────────────────────────────────────────────────────
# Ingestion
# ─────────────────────────────────────────────────────────────

def start_ingestion(kb_id: str, ds_id: str) -> None:
    """Trigger an ingestion job and wait for it to complete."""
    logger.info("Starting ingestion job...")

    response = bedrock_agent.start_ingestion_job(
        knowledgeBaseId=kb_id,
        dataSourceId=ds_id,
    )
    job_id = response["ingestionJob"]["ingestionJobId"]
    logger.info("Ingestion job started: %s — polling...", job_id)

    while True:
        status_resp = bedrock_agent.get_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id,
            ingestionJobId=job_id,
        )
        status = status_resp["ingestionJob"]["status"]
        stats = status_resp["ingestionJob"].get("statistics", {})
        logger.info("Status: %s | %s", status, stats)

        if status in ("COMPLETE", "FAILED", "STOPPED"):
            break
        time.sleep(10)

    if status != "COMPLETE":
        logger.error("Ingestion job ended with status: %s", status)
        sys.exit(1)

    logger.info("✅ Ingestion complete.")


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Create Bedrock Knowledge Base")
    parser.add_argument("--sync", action="store_true", help="Re-trigger ingestion using existing KB_ID")
    args = parser.parse_args()

    if args.sync:
        kb_id = os.environ.get("KB_ID", "")
        ds_id = os.environ.get("DATA_SOURCE_ID", "")
        if not kb_id or not ds_id:
            logger.error("KB_ID and DATA_SOURCE_ID must be set in .env for --sync mode.")
            sys.exit(1)
        start_ingestion(kb_id, ds_id)
    else:
        kb_id = create_knowledge_base()
        ds_id = create_data_source(kb_id)
        start_ingestion(kb_id, ds_id)

        # Persist IDs to .env
        set_key(ENV_FILE, "KB_ID", kb_id)
        set_key(ENV_FILE, "DATA_SOURCE_ID", ds_id)
        logger.info("💾 KB_ID=%s and DATA_SOURCE_ID=%s saved to .env", kb_id, ds_id)


if __name__ == "__main__":
    main()
