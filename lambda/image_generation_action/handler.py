"""
lambda/image_generation_action/handler.py
──────────────────────────────────────────
Action Group Lambda for the Bedrock Image Sub-Agent.
Handles the `generate_image` function call from the agent, invokes Titan Image
Generator v2, stores the resulting PNG in S3, and returns a presigned URL.

Bedrock Action Group event shape:
    {
        "actionGroup": "ImageGenerationActions",
        "function": "generate_image",
        "parameters": [
            {"name": "prompt", "value": "A futuristic data center..."}
        ]
    }

Response shape (Bedrock Action Group format):
    {
        "response": {
            "actionGroup": "...",
            "function": "generate_image",
            "functionResponse": {
                "responseBody": {
                    "TEXT": {
                        "body": "{\"image_url\": \"https://...\", \"prompt_used\": \"...\"}"
                    }
                }
            }
        }
    }
"""

import boto3
import json
import base64
import uuid
import os
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "eu-west-1")
BUCKET_NAME = os.environ.get("S3_IMAGES_BUCKET", "")
PRESIGNED_URL_EXPIRY = int(os.environ.get("PRESIGNED_URL_EXPIRY", "3600"))

bedrock_runtime = boto3.client("bedrock-runtime", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)


def _generate_image(prompt: str) -> dict:
    """Call Amazon Nova Canvas and return image bytes."""
    request_body = {
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {
            "text": prompt,
            "negativeText": "low quality, blurry, distorted, watermark, text overlay",
        },
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "height": 1024,
            "width": 1024,
            "cfgScale": 7.0,
        },
    }

    response = bedrock_runtime.invoke_model(
        modelId="amazon.nova-canvas-v1:0",
        body=json.dumps(request_body),
        contentType="application/json",
        accept="application/json",
    )

    result = json.loads(response["body"].read())
    return base64.b64decode(result["images"][0])


def _store_in_s3(image_bytes: bytes) -> str:
    """Upload PNG to S3 and return a presigned GET URL."""
    image_key = f"generated/{uuid.uuid4()}.png"

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=image_key,
        Body=image_bytes,
        ContentType="image/png",
    )

    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET_NAME, "Key": image_key},
        ExpiresIn=PRESIGNED_URL_EXPIRY,
    )

    logger.info("Image stored at s3://%s/%s", BUCKET_NAME, image_key)
    return url


def handler(event: dict, context) -> dict:
    """Lambda entry point — called by Bedrock Action Group."""
    action_group = event.get("actionGroup", "")
    function_name = event.get("function", "")
    parameters = {p["name"]: p["value"] for p in event.get("parameters", [])}

    logger.info("Action group: %s | Function: %s | Params: %s", action_group, function_name, parameters)

    if function_name != "generate_image":
        error_msg = f"Unknown function: {function_name}"
        logger.error(error_msg)
        response_body = json.dumps({"error": error_msg})
    else:
        prompt = parameters.get("prompt", "").strip()
        if not prompt:
            response_body = json.dumps({"error": "Parameter 'prompt' is required."})
        else:
            image_bytes = _generate_image(prompt)
            image_url = _store_in_s3(image_bytes)
            # Also include base64 for inline display
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            response_body = json.dumps({
                "image_url": image_url,
                "image_base64": image_base64,
                "prompt_used": prompt
            })

    return {
        "response": {
            "actionGroup": action_group,
            "function": function_name,
            "functionResponse": {
                "responseBody": {
                    "TEXT": {"body": response_body}
                }
            },
        }
    }
