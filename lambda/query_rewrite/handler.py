"""
lambda/query_rewrite/handler.py
────────────────────────────────
Rewrites the raw user query into a more retrieval-friendly form using
Claude Haiku via Bedrock InvokeModel.

Event shape:
    {"query": "<raw user question>"}

Response shape:
    {"original_query": "...", "rewritten_query": "..."}
"""

import boto3
import json
import os
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "eu-west-1")
MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

bedrock = boto3.client("bedrock-runtime", region_name=REGION)

REWRITE_PROMPT = """Rewrite the following user query to be more specific and \
retrieval-friendly. Remove ambiguity, expand abbreviations, and prefer noun \
phrases over pronouns. Return ONLY the rewritten query — no preamble, no \
explanation, no quotes.

Original query: {query}"""


def handler(event: dict, context) -> dict:
    """Lambda entry point."""
    original_query = event.get("query", "").strip()
    if not original_query:
        raise ValueError("Event must contain a non-empty 'query' field.")

    logger.info("Rewriting query: %s", original_query)

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 256,
        "messages": [
            {
                "role": "user",
                "content": REWRITE_PROMPT.format(query=original_query),
            }
        ],
    }

    response = bedrock.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )

    result = json.loads(response["body"].read())
    rewritten = result["content"][0]["text"].strip()

    logger.info("Rewritten query: %s", rewritten)

    return {
        "original_query": original_query,
        "rewritten_query": rewritten,
    }
