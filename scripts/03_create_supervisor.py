"""
scripts/03_create_supervisor.py
────────────────────────────────
Creates the Bedrock Supervisor Agent, registers the RAG and Image sub-agents as
collaborators, enables multi-agent orchestration, and prepares/aliases the supervisor.

Usage:
    python scripts/03_create_supervisor.py

Pre-requisites:
  - RAG_AGENT_ID, RAG_ALIAS_ID, IMAGE_AGENT_ID, IMAGE_ALIAS_ID set in .env (from script 02)

Writes SUPERVISOR_AGENT_ID and SUPERVISOR_ALIAS_ID to .env.
"""

import boto3
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
BEDROCK_AGENT_ROLE_ARN = os.environ["BEDROCK_AGENT_ROLE_ARN"]
RAG_AGENT_ID = os.environ["RAG_AGENT_ID"]
RAG_ALIAS_ID = os.environ["RAG_ALIAS_ID"]
IMAGE_AGENT_ID = os.environ["IMAGE_AGENT_ID"]
IMAGE_ALIAS_ID = os.environ["IMAGE_ALIAS_ID"]

ENV_FILE = os.path.join(os.path.dirname(__file__), "..", ".env")

bedrock_agent = boto3.client("bedrock-agent", region_name=REGION)

SUPERVISOR_INSTRUCTION = """You are a supervisor coordinating a team of specialist AI agents. \
Your role is to understand the user's intent and delegate tasks to the right specialist.

Team members:
- RAG Specialist: Retrieves accurate, cited information from company documents and knowledge bases. \
  Use for: policy questions, internal reports, documentation lookups, factual company data.
- Image Specialist: Generates high-quality images from text descriptions using Titan Image Generator. \
  Use for: any request to create, visualize, draw, or render images or diagrams.

Orchestration rules:
1. For document/knowledge questions → delegate to RAG Specialist.
2. For image/visualization requests → delegate to Image Specialist.
3. For requests requiring both → invoke both and synthesize the combined response.
4. For general questions within your own knowledge → answer directly without delegation.
5. Always synthesize sub-agent responses into a single, coherent final answer.
6. When the RAG Specialist returns source citations, include them in your response.
7. If a sub-agent cannot confidently answer, try rephrasing or use a different approach \
   rather than returning a low-quality response to the user."""


def _wait_for_agent(agent_id: str, target_status: str = "NOT_PREPARED") -> None:
    for _ in range(30):
        resp = bedrock_agent.get_agent(agentId=agent_id)
        status = resp["agent"]["agentStatus"]
        logger.info("Agent %s status: %s", agent_id, status)
        if status == target_status:
            return
        if "FAILED" in status:
            raise RuntimeError(f"Agent {agent_id} reached failed state: {status}")
        time.sleep(5)
    raise TimeoutError(f"Agent {agent_id} did not reach {target_status} in time.")


def create_supervisor() -> str:
    """Create the Supervisor Agent."""
    logger.info("Creating Supervisor Agent...")

    resp = bedrock_agent.create_agent(
        agentName="multi-agent-supervisor",
        agentResourceRoleArn=BEDROCK_AGENT_ROLE_ARN,
        foundationModel="anthropic.claude-3-5-sonnet-20241022-v2:0",
        instruction=SUPERVISOR_INSTRUCTION,
        idleSessionTTLInSeconds=600,
        tags={"Project": "multi-agent-bedrock", "Role": "supervisor"},
    )

    supervisor_id = resp["agent"]["agentId"]
    logger.info("Supervisor agent created: %s", supervisor_id)
    return supervisor_id


def register_collaborators(supervisor_id: str) -> None:
    """Register sub-agents as collaborators on the Supervisor."""
    collaborators = [
        {
            "agent_id": RAG_AGENT_ID,
            "alias_id": RAG_ALIAS_ID,
            "name": "rag-specialist",
            "instruction": (
                "Retrieves accurate, cited information from company knowledge bases and documents. "
                "Use for policy questions, internal reports, and factual company data."
            ),
        },
        {
            "agent_id": IMAGE_AGENT_ID,
            "alias_id": IMAGE_ALIAS_ID,
            "name": "image-specialist",
            "instruction": (
                "Generates high-quality images from text descriptions using Titan Image Generator. "
                "Use for any image creation, visualization, or diagram request."
            ),
        },
    ]

    for collab in collaborators:
        alias_arn = (
            f"arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:agent-alias"
            f"/{collab['agent_id']}/{collab['alias_id']}"
        )
        logger.info("Registering collaborator '%s' (%s)...", collab["name"], alias_arn)

        bedrock_agent.associate_agent_collaborator(
            agentId=supervisor_id,
            agentVersion="DRAFT",
            agentDescriptor={"aliasArn": alias_arn},
            collaboratorName=collab["name"],
            collaborationInstruction=collab["instruction"],
            relayConversationHistory="TO_COLLABORATOR",  # sub-agents receive conversation context
        )
        logger.info("✅ Collaborator '%s' registered.", collab["name"])


def enable_orchestration(supervisor_id: str) -> None:
    """Enable multi-agent collaboration (Supervisor pattern) on the agent."""
    logger.info("Enabling multi-agent orchestration on supervisor %s...", supervisor_id)

    # Fetch current agent config to preserve all required fields
    current = bedrock_agent.get_agent(agentId=supervisor_id)["agent"]

    bedrock_agent.update_agent(
        agentId=supervisor_id,
        agentName=current["agentName"],
        agentResourceRoleArn=current["agentResourceRoleArn"],
        foundationModel=current["foundationModel"],
        instruction=current["instruction"],
        # Enable supervisor pattern — the agent will orchestrate via sub-agent calls
        orchestrationType="DEFAULT",
    )
    logger.info("✅ Orchestration type set to DEFAULT (Supervisor pattern).")


def prepare_and_alias(supervisor_id: str) -> str:
    """Prepare the supervisor draft and create a production alias."""
    logger.info("Preparing supervisor agent %s...", supervisor_id)
    bedrock_agent.prepare_agent(agentId=supervisor_id)
    _wait_for_agent(supervisor_id, target_status="PREPARED")

    alias_resp = bedrock_agent.create_agent_alias(
        agentId=supervisor_id,
        agentAliasName="production-v1",
        tags={"Project": "multi-agent-bedrock"},
    )
    alias_id = alias_resp["agentAlias"]["agentAliasId"]
    logger.info("✅ Supervisor alias created: %s", alias_id)
    return alias_id


def main():
    _wait_for_agent(RAG_AGENT_ID, target_status="PREPARED")
    _wait_for_agent(IMAGE_AGENT_ID, target_status="PREPARED")

    supervisor_id = create_supervisor()
    _wait_for_agent(supervisor_id)

    register_collaborators(supervisor_id)
    enable_orchestration(supervisor_id)

    supervisor_alias_id = prepare_and_alias(supervisor_id)

    set_key(ENV_FILE, "SUPERVISOR_AGENT_ID", supervisor_id)
    set_key(ENV_FILE, "SUPERVISOR_ALIAS_ID", supervisor_alias_id)

    logger.info("\n✅ Supervisor created successfully:")
    logger.info("  Supervisor Agent: %s / %s", supervisor_id, supervisor_alias_id)
    logger.info("  IDs saved to .env")


if __name__ == "__main__":
    main()
