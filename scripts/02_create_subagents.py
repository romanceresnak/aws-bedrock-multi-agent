"""
scripts/02_create_subagents.py
───────────────────────────────
Creates two Bedrock Sub-Agents:
  1. RAG Specialist — associated with the Knowledge Base
  2. Image Generation Specialist — has an action group backed by the image Lambda

Usage:
    python scripts/02_create_subagents.py

Pre-requisites:
  - KB_ID set in .env (from script 01)
  - IMAGE_ACTION_LAMBDA_ARN set in .env (from Terraform outputs)

Writes RAG_AGENT_ID, RAG_ALIAS_ID, IMAGE_AGENT_ID, IMAGE_ALIAS_ID to .env.
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
KB_ID = os.environ["KB_ID"]
IMAGE_ACTION_LAMBDA_ARN = os.environ["IMAGE_ACTION_LAMBDA_ARN"]

ENV_FILE = os.path.join(os.path.dirname(__file__), "..", ".env")

bedrock_agent = boto3.client("bedrock-agent", region_name=REGION)


# ─────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────

def _wait_for_agent(agent_id: str, target_status: str = "NOT_PREPARED") -> None:
    """Poll until the agent reaches the expected status."""
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


def _prepare_and_alias(agent_id: str, alias_name: str = "production-v1") -> str:
    """Prepare the agent draft and create an alias. Returns alias ID."""
    logger.info("Preparing agent %s...", agent_id)
    bedrock_agent.prepare_agent(agentId=agent_id)
    _wait_for_agent(agent_id, target_status="PREPARED")

    logger.info("Creating alias '%s' for agent %s...", alias_name, agent_id)
    alias_resp = bedrock_agent.create_agent_alias(
        agentId=agent_id,
        agentAliasName=alias_name,
        tags={"Project": "multi-agent-bedrock"},
    )
    alias_id = alias_resp["agentAlias"]["agentAliasId"]
    logger.info("✅ Alias created: %s", alias_id)
    return alias_id


# ─────────────────────────────────────────────────────────────
# RAG Sub-Agent
# ─────────────────────────────────────────────────────────────

def create_rag_agent() -> tuple[str, str]:
    """Create the RAG specialist sub-agent and associate the Knowledge Base."""
    logger.info("Creating RAG Sub-Agent...")

    resp = bedrock_agent.create_agent(
        agentName="rag-specialist-agent",
        agentResourceRoleArn=BEDROCK_AGENT_ROLE_ARN,
        foundationModel="anthropic.claude-3-sonnet-20240229-v1:0",
        instruction=(
            "You are a document retrieval specialist. Your only job is to find "
            "relevant information from the company knowledge base and return accurate, "
            "well-cited answers.\n\n"
            "Rules:\n"
            "- Always include the source document URI in your response.\n"
            "- If the answer is not in the knowledge base, say so explicitly — do not guess.\n"
            "- Return answers in clear, structured markdown.\n"
            "- Prefer quoting directly from the source over paraphrasing when accuracy matters."
        ),
        idleSessionTTLInSeconds=300,
        tags={"Project": "multi-agent-bedrock", "Role": "rag-specialist"},
    )

    rag_agent_id = resp["agent"]["agentId"]
    logger.info("RAG agent created: %s", rag_agent_id)

    _wait_for_agent(rag_agent_id)

    # Associate Knowledge Base
    bedrock_agent.associate_agent_knowledge_base(
        agentId=rag_agent_id,
        agentVersion="DRAFT",
        knowledgeBaseId=KB_ID,
        description="Primary company documentation knowledge base",
        knowledgeBaseState="ENABLED",
    )
    logger.info("Knowledge Base %s associated with RAG agent.", KB_ID)

    alias_id = _prepare_and_alias(rag_agent_id)
    return rag_agent_id, alias_id


# ─────────────────────────────────────────────────────────────
# Image Sub-Agent
# ─────────────────────────────────────────────────────────────

def create_image_agent() -> tuple[str, str]:
    """Create the image generation specialist sub-agent with an action group."""
    logger.info("Creating Image Sub-Agent...")

    resp = bedrock_agent.create_agent(
        agentName="image-generation-agent",
        agentResourceRoleArn=BEDROCK_AGENT_ROLE_ARN,
        foundationModel="anthropic.claude-3-sonnet-20240229-v1:0",
        instruction=(
            "You are an image generation specialist. When a user asks you to create, "
            "visualize, draw, or render any image or diagram, use the generate_image function.\n\n"
            "Rules:\n"
            "- Always describe what you are about to generate before calling the function.\n"
            "- Write detailed, descriptive prompts — include style, lighting, and composition.\n"
            "- Return the image URL to the user after generation along with the prompt used.\n"
            "- If the request is ambiguous, ask one clarifying question before generating."
        ),
        idleSessionTTLInSeconds=300,
        tags={"Project": "multi-agent-bedrock", "Role": "image-specialist"},
    )

    image_agent_id = resp["agent"]["agentId"]
    logger.info("Image agent created: %s", image_agent_id)

    _wait_for_agent(image_agent_id)

    # Attach action group
    bedrock_agent.create_agent_action_group(
        agentId=image_agent_id,
        agentVersion="DRAFT",
        actionGroupName="ImageGenerationActions",
        description="Tools for generating images from text descriptions using Titan Image Generator.",
        actionGroupState="ENABLED",
        actionGroupExecutor={"lambda": IMAGE_ACTION_LAMBDA_ARN},
        functionSchema={
            "functions": [
                {
                    "name": "generate_image",
                    "description": (
                        "Generate a high-quality image from a detailed text description "
                        "using Amazon Titan Image Generator v2."
                    ),
                    "parameters": {
                        "prompt": {
                            "description": (
                                "Detailed text description of the image to generate. "
                                "Include style, colours, composition, and mood for best results."
                            ),
                            "type": "string",
                            "required": True,
                        }
                    },
                }
            ]
        },
    )
    logger.info("Action group 'ImageGenerationActions' attached to agent %s.", image_agent_id)

    alias_id = _prepare_and_alias(image_agent_id)
    return image_agent_id, alias_id


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main():
    rag_agent_id, rag_alias_id = create_rag_agent()
    image_agent_id, image_alias_id = create_image_agent()

    set_key(ENV_FILE, "RAG_AGENT_ID", rag_agent_id)
    set_key(ENV_FILE, "RAG_ALIAS_ID", rag_alias_id)
    set_key(ENV_FILE, "IMAGE_AGENT_ID", image_agent_id)
    set_key(ENV_FILE, "IMAGE_ALIAS_ID", image_alias_id)

    logger.info("\n✅ Sub-agents created successfully:")
    logger.info("  RAG Agent:   %s / %s", rag_agent_id, rag_alias_id)
    logger.info("  Image Agent: %s / %s", image_agent_id, image_alias_id)
    logger.info("  IDs saved to .env")


if __name__ == "__main__":
    main()
