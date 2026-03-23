#!/usr/bin/env python3
"""
Add action group to Supervisor agent to enable delegation to RAG agent.
"""

import os
import json
import boto3
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv('AWS_REGION')
SUPERVISOR_AGENT_ID = os.getenv('SUPERVISOR_AGENT_ID')
INVOKE_RAG_LAMBDA_ARN = f"arn:aws:lambda:{AWS_REGION}:{os.getenv('AWS_ACCOUNT_ID')}:function:multi-agent-bedrock-dev-invoke-rag-agent"

bedrock_agent = boto3.client('bedrock-agent', region_name=AWS_REGION)

def add_action_group():
    """Add SearchDocuments action group to Supervisor agent."""

    print(f"Adding action group to Supervisor agent {SUPERVISOR_AGENT_ID}...")

    # Define the action group schema
    function_schema = {
        "functions": [
            {
                "name": "search_documents",
                "description": "Search company documents and knowledge base for specific information. Use this when users ask about company policies, procedures, guidelines, or any documented information.",
                "parameters": {
                    "query": {
                        "description": "The search query to find relevant information in company documents",
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
            actionGroupName='SearchDocumentsActions',
            description='Delegates document search queries to the specialized RAG agent',
            actionGroupExecutor={
                'lambda': INVOKE_RAG_LAMBDA_ARN
            },
            functionSchema={
                'functions': function_schema['functions']
            },
            actionGroupState='ENABLED'
        )

        action_group_id = response['agentActionGroup']['actionGroupId']
        print(f"✅ Action group created: {action_group_id}")
        print(f"   Name: SearchDocumentsActions")
        print(f"   Lambda: {INVOKE_RAG_LAMBDA_ARN}")
        print(f"   Function: search_documents")

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
            if ag['actionGroupName'] == 'SearchDocumentsActions':
                action_group_id = ag['actionGroupId']
                break

        if action_group_id:
            # Update existing action group
            response = bedrock_agent.update_agent_action_group(
                agentId=SUPERVISOR_AGENT_ID,
                agentVersion='DRAFT',
                actionGroupId=action_group_id,
                actionGroupName='SearchDocumentsActions',
                description='Delegates document search queries to the specialized RAG agent',
                actionGroupExecutor={
                    'lambda': INVOKE_RAG_LAMBDA_ARN
                },
                functionSchema={
                    'functions': function_schema['functions']
                },
                actionGroupState='ENABLED'
            )
            print(f"✅ Action group updated: {action_group_id}")

        return action_group_id


def update_supervisor_instruction():
    """Update Supervisor agent instruction to include delegation logic."""

    print(f"\nUpdating Supervisor agent instruction...")

    instruction = """You are a supervisor agent that coordinates multiple specialized agents to answer user queries.

**Your Capabilities:**

1. **Document Search**: You have access to a search_documents function that queries the company knowledge base. Use this function when users ask about:
   - Company policies (remote work, benefits, procedures, etc.)
   - Guidelines and documentation
   - Any specific information that might be in company documents

2. **General Assistance**: For general questions, greetings, or conversations that don't require document lookup, respond directly.

**When to Use search_documents:**
- User asks "What is our remote work policy?" → Use search_documents
- User asks "What are the company benefits?" → Use search_documents
- User asks about any policy, procedure, or documented information → Use search_documents

**When to Respond Directly:**
- User says "Hello" or general greetings → Respond directly
- User asks general questions that don't need specific documentation → Respond directly
- User asks about capabilities → Explain what you can do

**Response Format:**
- When using search_documents, wait for the results and present them clearly to the user
- Include any citations or sources provided by the search results
- Be concise and helpful

Always determine if a query needs document search before responding."""

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
    print("Adding Action Group to Supervisor Agent")
    print("=" * 60)

    # Step 1: Add action group
    action_group_id = add_action_group()

    if action_group_id:
        # Step 2: Update instruction
        update_supervisor_instruction()

        # Step 3: Prepare agent
        prepare_agent()

        print("\n" + "=" * 60)
        print("✅ SETUP COMPLETE")
        print("=" * 60)
        print(f"\nSupervisor Agent ID: {SUPERVISOR_AGENT_ID}")
        print(f"Action Group: SearchDocumentsActions")
        print(f"Function: search_documents")
        print("\nNext: Test with a query like 'What is our remote work policy?'")
    else:
        print("\n❌ Failed to add action group")
