"""
Lambda function to invoke RAG agent for document search.
This enables the Supervisor agent to delegate document queries to the RAG specialist.
"""

import json
import os
import boto3
import logging
from typing import Dict, Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize Bedrock client
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=os.environ.get('AWS_REGION_OVERRIDE', 'eu-west-1'))

RAG_AGENT_ID = os.environ['RAG_AGENT_ID']
RAG_ALIAS_ID = os.environ['RAG_ALIAS_ID']


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Invoke RAG agent with a document search query.

    Expected event format (from Bedrock action group):
    {
        "actionGroup": "SearchDocumentsActions",
        "function": "search_documents",
        "parameters": [
            {"name": "query", "value": "What is the remote work policy?"}
        ]
    }
    """

    logger.info(f"Received event: {json.dumps(event)}")

    try:
        # Extract query from parameters
        parameters = event.get('parameters', [])
        query = None

        for param in parameters:
            if param.get('name') == 'query':
                query = param.get('value')
                break

        if not query:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Missing required parameter: query'
                })
            }

        logger.info(f"Invoking RAG agent with query: {query}")

        # Invoke RAG agent
        response = bedrock_agent_runtime.invoke_agent(
            agentId=RAG_AGENT_ID,
            agentAliasId=RAG_ALIAS_ID,
            sessionId=event.get('sessionId', 'lambda-session'),
            inputText=query,
            enableTrace=True
        )

        # Collect response
        full_response = ''
        citations = []

        for event_item in response['completion']:
            if 'chunk' in event_item:
                chunk_text = event_item['chunk']['bytes'].decode('utf-8')
                full_response += chunk_text

            # Extract citations from trace
            if 'trace' in event_item:
                trace = event_item.get('trace', {}).get('trace', {})
                if 'orchestrationTrace' in trace:
                    orch = trace['orchestrationTrace']
                    if 'observation' in orch:
                        obs = orch['observation']
                        if 'knowledgeBaseLookupOutput' in obs:
                            kb_output = obs['knowledgeBaseLookupOutput']
                            if 'retrievedReferences' in kb_output:
                                for ref in kb_output['retrievedReferences']:
                                    location = ref.get('location', {}).get('s3Location', {})
                                    uri = location.get('uri', '')
                                    if uri and uri not in citations:
                                        citations.append(uri)

        logger.info(f"RAG agent response: {full_response[:100]}...")
        logger.info(f"Citations: {citations}")

        # Format response for Bedrock action group
        result = {
            'response': full_response,
            'citations': citations
        }

        # Return in the format expected by Bedrock action groups
        return {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': event.get('actionGroup', 'SearchDocumentsActions'),
                'function': event.get('function', 'search_documents'),
                'functionResponse': {
                    'responseBody': {
                        'TEXT': {
                            'body': json.dumps(result)
                        }
                    }
                }
            }
        }

    except Exception as e:
        logger.error(f"Error invoking RAG agent: {str(e)}", exc_info=True)

        return {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': event.get('actionGroup', 'SearchDocumentsActions'),
                'function': event.get('function', 'search_documents'),
                'functionResponse': {
                    'responseBody': {
                        'TEXT': {
                            'body': json.dumps({
                                'error': f'Failed to search documents: {str(e)}'
                            })
                        }
                    }
                }
            }
        }
