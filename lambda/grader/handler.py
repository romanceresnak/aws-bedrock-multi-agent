"""
lambda/grader/handler.py
─────────────────────────
Evaluates the quality of a Bedrock Supervisor Agent response using Claude Haiku.
Returns a structured JSON grade and decides whether to retry.

Event shape:
    {
        "rewritten_query": "...",
        "agent_response": "...",
        "retry_count": 0          # optional, defaults to 0
    }

Response shape (merged with input event + grade):
    {
        "rewritten_query": "...",
        "agent_response": "...",
        "retry_count": 1,
        "grade": {
            "score": 4,
            "reasoning": "Response is accurate and well-cited.",
            "should_retry": false
        }
    }
"""

import boto3
import json
import os
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "eu-west-1")
MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"
MAX_RETRIES = 3

bedrock = boto3.client("bedrock-runtime", region_name=REGION)

GRADER_SYSTEM = """You are a response quality evaluator for an AI assistant system.
Evaluate the agent response against the user query.

Respond ONLY with a valid JSON object — no markdown, no preamble:
{
  "score": <integer 1-5>,
  "reasoning": "<one concise sentence explaining the score>",
  "should_retry": <true if score <= 2, false otherwise>
}

Scoring rubric:
5 — Fully answers the query, accurate, well-cited
4 — Mostly answers the query, minor gaps
3 — Partially answers, key info missing or unclear
2 — Barely relevant or substantially incorrect
1 — Off-topic or harmful"""


def handler(event: dict, context) -> dict:
    """Lambda entry point."""
    query = event.get("rewritten_query", "").strip()
    response_text = event.get("agent_response", "").strip()
    retry_count = int(event.get("retry_count", 0))

    if not query or not response_text:
        raise ValueError("Event must contain 'rewritten_query' and 'agent_response'.")

    logger.info("Grading response (retry_count=%d)", retry_count)

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 256,
        "system": GRADER_SYSTEM,
        "messages": [
            {
                "role": "user",
                "content": f"Query: {query}\n\nAgent Response: {response_text}",
            }
        ],
    }

    eval_response = bedrock.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )

    result = json.loads(eval_response["body"].read())
    raw_grade_text = result["content"][0]["text"].strip()

    try:
        grade = json.loads(raw_grade_text)
    except json.JSONDecodeError:
        logger.error("Grader returned invalid JSON: %s", raw_grade_text)
        # Default to passing to avoid infinite retry loops
        grade = {"score": 3, "reasoning": "Grade parse error — defaulting to pass.", "should_retry": False}

    # Hard stop after MAX_RETRIES regardless of score
    if retry_count >= MAX_RETRIES:
        logger.info("Max retries (%d) reached — forcing should_retry=False", MAX_RETRIES)
        grade["should_retry"] = False

    new_retry_count = retry_count + (1 if grade.get("should_retry") else 0)

    logger.info("Grade: score=%d, should_retry=%s", grade.get("score"), grade.get("should_retry"))

    return {
        **event,
        "grade": grade,
        "retry_count": new_retry_count,
    }
