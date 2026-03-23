#!/usr/bin/env python3
"""
Add image generation action group to Supervisor agent.
"""

import os
import boto3
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv('AWS_REGION')
SUPERVISOR_AGENT_ID = os.getenv('SUPERVISOR_AGENT_ID')
IMAGE_ACTION_LAMBDA_ARN = os.getenv('IMAGE_ACTION_LAMBDA_ARN')

bedrock_agent = boto3.client('bedrock-agent', region_name=AWS_REGION)


def add_image_action_group():
    """Add ImageGeneration action group to Supervisor agent."""

    print(f"Adding image generation action group to Supervisor agent {SUPERVISOR_AGENT_ID}...")

    # Define the action group schema
    function_schema = {
        "functions": [
            {
                "name": "generate_image",
                "description": "Generate an image based on a text description using AI. Use this when users ask to create, generate, draw, or visualize images.",
                "parameters": {
                    "prompt": {
                        "description": "Detailed text description of the image to generate. Be specific about style, colors, objects, and composition.",
                        "required": True,
                        "type": "string"
                    }
                }
            }
        ]
    }

    try:
        response = bedrock_agent.create_agent_action_group(
            agentId=SUPERVISOR_AGENT_ID,
            agentVersion='DRAFT',
            actionGroupName='ImageGenerationActions',
            description='Delegates image generation requests to Amazon Nova Canvas',
            actionGroupExecutor={
                'lambda': IMAGE_ACTION_LAMBDA_ARN
            },
            functionSchema={
                'functions': function_schema['functions']
            },
            actionGroupState='ENABLED'
        )

        action_group_id = response['agentActionGroup']['actionGroupId']
        print(f"✅ Action group created: {action_group_id}")
        print(f"   Name: ImageGenerationActions")
        print(f"   Lambda: {IMAGE_ACTION_LAMBDA_ARN}")
        print(f"   Function: generate_image")

        return action_group_id

    except bedrock_agent.exceptions.ConflictException:
        print("⚠️  Action group already exists. Updating...")

        # List existing action groups to get the ID
        list_response = bedrock_agent.list_agent_action_groups(
            agentId=SUPERVISOR_AGENT_ID,
            agentVersion='DRAFT'
        )

        action_group_id = None
        for ag in list_response.get('actionGroupSummaries', []):
            if ag['actionGroupName'] == 'ImageGenerationActions':
                action_group_id = ag['actionGroupId']
                break

        if action_group_id:
            # Update existing action group
            response = bedrock_agent.update_agent_action_group(
                agentId=SUPERVISOR_AGENT_ID,
                agentVersion='DRAFT',
                actionGroupId=action_group_id,
                actionGroupName='ImageGenerationActions',
                description='Delegates image generation requests to Amazon Nova Canvas',
                actionGroupExecutor={
                    'lambda': IMAGE_ACTION_LAMBDA_ARN
                },
                functionSchema={
                    'functions': function_schema['functions']
                },
                actionGroupState='ENABLED'
            )
            print(f"✅ Action group updated: {action_group_id}")

        return action_group_id


def update_supervisor_instruction():
    """Update Supervisor agent instruction to include image generation."""

    print(f"\nUpdating Supervisor agent instruction...")

    instruction = """You are a supervisor agent that coordinates multiple specialized agents to answer user queries.

**Your Capabilities:**

1. **Document Search**: You have access to a search_documents function that queries the company knowledge base. Use this when users ask about:
   - Company policies (remote work, benefits, procedures, etc.)
   - Guidelines and documentation
   - Any specific information that might be in company documents

2. **Image Generation**: You have access to a generate_image function that creates images using AI. Use this when users ask to:
   - Create, generate, draw, or make images
   - Visualize concepts or ideas
   - Design graphics or illustrations
   - Examples: "generate an image of...", "create a picture of...", "draw me a..."

3. **General Assistance**: For general questions, greetings, or conversations that don't require document lookup or image generation, respond directly.

**When to Use search_documents:**
- User asks "What is our remote work policy?" → Use search_documents
- User asks "What are the company benefits?" → Use search_documents
- User asks about any policy, procedure, or documented information → Use search_documents

**When to Use generate_image:**
- User asks "Generate an image of a sunset" → Use generate_image with prompt "sunset"
- User asks "Create a picture of a futuristic city" → Use generate_image
- User asks "Draw me a mountain landscape" → Use generate_image
- User asks to visualize anything → Use generate_image

**When to Respond Directly:**
- User says "Hello" or general greetings → Respond directly
- User asks general questions that don't need specific documentation → Respond directly
- User asks about your capabilities → Explain what you can do

**Response Format:**
- When using search_documents, wait for the results and present them clearly to the user with any citations
- When using generate_image, wait for the result and provide the image URL to the user
- Be concise and helpful

Always determine if a query needs document search, image generation, or direct response before responding."""

    try:
        # Get current agent configuration
        agent_response = bedrock_agent.get_agent(
            agentId=SUPERVISOR_AGENT_ID
        )

        # Update agent with new instruction
        update_response = bedrock_agent.update_agent(
            agentId=SUPERVISOR_AGENT_ID,
            agentName=agent_response['agent']['agentName'],
            instruction=instruction,
            foundationModel=agent_response['agent']['foundationModel'],
            agentResourceRoleArn=agent_response['agent']['agentResourceRoleArn']
        )

        print(f"✅ Supervisor instruction updated")

    except Exception as e:
        print(f"❌ Error updating instruction: {e}")


def prepare_agent():
    """Prepare the agent to activate changes."""

    print(f"\nPreparing Supervisor agent to activate changes...")

    try:
        response = bedrock_agent.prepare_agent(
            agentId=SUPERVISOR_AGENT_ID
        )

        status = response['agentStatus']
        print(f"✅ Agent preparation initiated. Status: {status}")
        print("   Wait 30-60 seconds for agent to be ready for testing.")

    except Exception as e:
        print(f"❌ Error preparing agent: {e}")


if __name__ == '__main__':
    print("=" * 60)
    print("Adding Image Generation to Supervisor Agent")
    print("=" * 60)

    # Step 1: Add action group
    action_group_id = add_image_action_group()

    if action_group_id:
        # Step 2: Update instruction
        update_supervisor_instruction()

        # Step 3: Prepare agent
        prepare_agent()

        print("\n" + "=" * 60)
        print("✅ SETUP COMPLETE")
        print("=" * 60)
        print(f"\nSupervisor Agent ID: {SUPERVISOR_AGENT_ID}")
        print(f"Action Groups:")
        print(f"  1. SearchDocumentsActions → RAG Agent")
        print(f"  2. ImageGenerationActions → Nova Canvas")
        print("\nNext: Test in Console with:")
        print('  - "What is our remote work policy?" (RAG)')
        print('  - "Generate an image of a sunset over mountains" (Image)')
    else:
        print("\n❌ Failed to add action group")
