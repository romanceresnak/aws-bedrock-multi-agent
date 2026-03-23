"""
lambda/orchestrator/handler.py
───────────────────────────────
Top-level API Gateway → Lambda entry point.
Chains: Query Rewrite → Supervisor Agent (with retry loop) → Grader → A2I submit.

Returns HTTP 202 immediately — human review is asynchronous.

Event shape (from API Gateway proxy integration):
    {
        "body": "{\"query\": \"What is our remote work policy?\"}"
    }

Response shape:
    {
        "statusCode": 202,
        "headers": {...},
        "body": "{\"session_id\": \"...\", \"human_loop_arn\": \"...\", ...}"
    }
"""

import boto3
import json
import uuid
import os
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "eu-west-1")
SUPERVISOR_AGENT_ID = os.environ["SUPERVISOR_AGENT_ID"]
SUPERVISOR_ALIAS_ID = os.environ["SUPERVISOR_ALIAS_ID"]
QUERY_REWRITE_FN = os.environ.get("QUERY_REWRITE_LAMBDA_ARN", "query-rewrite-fn")
GRADER_FN = os.environ.get("GRADER_LAMBDA_ARN", "grader-fn")
A2I_FLOW_ARN = os.environ.get("A2I_FLOW_ARN", "")
MAX_RETRIES = 3

lambda_client = boto3.client("lambda", region_name=REGION)
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)
a2i = boto3.client("sagemaker-a2i-runtime", region_name=REGION)


# ─────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────

def _invoke_lambda(function_name: str, payload: dict) -> dict:
    """Synchronously invoke another Lambda and return its response payload."""
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload),
    )
    return json.loads(response["Payload"].read())


def _invoke_supervisor(query: str, session_id: str) -> dict:
    """Invoke the Bedrock Supervisor Agent and collect response + trace events."""
    response = bedrock_agent_runtime.invoke_agent(
        agentId=SUPERVISOR_AGENT_ID,
        agentAliasId=SUPERVISOR_ALIAS_ID,
        sessionId=session_id,
        inputText=query,
        enableTrace=True,
    )

    full_response = ""
    trace_events = []

    for event in response["completion"]:
        if "chunk" in event:
            full_response += event["chunk"]["bytes"].decode("utf-8")

        if "trace" in event:
            trace = event["trace"].get("trace", {})
            orch = trace.get("orchestrationTrace", {})
            inv_input = orch.get("invocationInput", {})

            if inv_input.get("invocationType") == "AGENT_COLLABORATOR":
                collab = inv_input.get("agentCollaboratorInvocationInput", {})
                trace_events.append({
                    "type": "sub_agent_call",
                    "agent": collab.get("agentCollaboratorName", "unknown"),
                    "input": collab.get("input", {}).get("text", ""),
                })

    return {
        "answer": full_response,
        "sub_agents_called": trace_events,
    }


def _submit_for_review(query: str, agent_response: str, grade: dict) -> str:
    """Submit the approved response for human review via A2I. Returns HumanLoopArn."""
    if not A2I_FLOW_ARN:
        logger.warning("A2I_FLOW_ARN not set — skipping human review submission.")
        return ""

    loop_name = f"review-{uuid.uuid4().hex[:12]}"

    response = a2i.start_human_loop(
        HumanLoopName=loop_name,
        FlowDefinitionArn=A2I_FLOW_ARN,
        HumanLoopInput={
            "InputContent": json.dumps({
                "query": query,
                "agent_response": agent_response,
                "auto_grade": grade,
                "instructions": (
                    "Review the agent response for accuracy and appropriateness. "
                    "Approve or reject with an optional comment."
                ),
            })
        },
        DataAttributes={"ContentClassifiers": ["FreeOfPersonallyIdentifiableInformation"]},
    )

    return response["HumanLoopArn"]


# ─────────────────────────────────────────────────────────────
# Lambda entry point
# ─────────────────────────────────────────────────────────────

def handler(event: dict, context) -> dict:
    """Main orchestration handler called from API Gateway."""
    # Parse body — API Gateway wraps the body as a JSON string
    body = event.get("body") or "{}"
    if isinstance(body, str):
        body = json.loads(body)

    raw_query = body.get("query", "").strip()
    if not raw_query:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Request body must contain 'query'."}),
        }

    session_id = str(uuid.uuid4())
    logger.info("New request — session_id=%s query=%s", session_id, raw_query)

    # ── Step 1: Query Rewrite ──────────────────────────────
    rewrite_result = _invoke_lambda(QUERY_REWRITE_FN, {"query": raw_query})
    rewritten_query = rewrite_result.get("rewritten_query", raw_query)
    logger.info("Rewritten query: %s", rewritten_query)

    # ── Step 2 + 3: Supervisor + Grader (retry loop) ───────
    retry_count = 0
    supervisor_result = {}
    grade = {"score": 0, "reasoning": "Not evaluated", "should_retry": False}

    while retry_count <= MAX_RETRIES:
        supervisor_result = _invoke_supervisor(rewritten_query, session_id)
        logger.info(
            "Supervisor response (attempt %d): %d chars, sub_agents=%s",
            retry_count + 1,
            len(supervisor_result["answer"]),
            [e["agent"] for e in supervisor_result["sub_agents_called"]],
        )

        grade_response = _invoke_lambda(
            GRADER_FN,
            {
                "rewritten_query": rewritten_query,
                "agent_response": supervisor_result["answer"],
                "retry_count": retry_count,
            },
        )
        grade = grade_response.get("grade", {})

        if not grade.get("should_retry", False):
            logger.info("Grade accepted: score=%d", grade.get("score"))
            break

        retry_count += 1
        logger.warning("Grade too low (score=%d) — retrying (%d/%d)", grade.get("score"), retry_count, MAX_RETRIES)

    # ── Step 4: Human-in-the-Loop ─────────────────────────
    human_loop_arn = _submit_for_review(
        query=rewritten_query,
        agent_response=supervisor_result.get("answer", ""),
        grade=grade,
    )

    # Return 202 — human review is async
    return {
        "statusCode": 202,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({
            "session_id": session_id,
            "original_query": raw_query,
            "rewritten_query": rewritten_query,
            "answer": supervisor_result.get("answer", ""),
            "auto_grade": grade,
            "sub_agents_used": supervisor_result.get("sub_agents_called", []),
            "human_loop_arn": human_loop_arn,
            "status": "pending_human_review" if human_loop_arn else "completed",
        }),
    }
