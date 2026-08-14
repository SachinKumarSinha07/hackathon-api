"""
AWS Bedrock client.

The only module that knows about Bedrock/AWS SDK specifics. Callers pass a system
prompt plus a plain conversation history and receive streamed text chunks.
"""

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError, ReadTimeoutError
from functools import lru_cache
from typing import Dict, Generator, List
import os

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_THROTTLING_CODES = {
    "ThrottlingException",
    "TooManyRequestsException",
    "ServiceQuotaExceededException",
}
_AUTH_CODES = {
    "AccessDeniedException",
    "UnrecognizedClientException",
    "ExpiredTokenException",
    "InvalidSignatureException",
}
_TIMEOUT_CODES = {
    "ModelTimeoutException",
    "ServiceUnavailableException",
    "ModelNotReadyException",
}

# Model id markers for models that reject the `temperature` inference parameter.
_NO_TEMPERATURE_MARKERS = ("sonnet-5",)


def _model_supports_temperature(model_id: str) -> bool:
    """Whether the model accepts a `temperature` parameter (Sonnet 5 does not)."""
    lowered = model_id.lower()
    return not any(marker in lowered for marker in _NO_TEMPERATURE_MARKERS)


class BedrockError(Exception):
    """Raised when a Bedrock call cannot be completed. Carries a user-safe message."""

    def __init__(self, message: str, retryable: bool = False):
        self.message = message
        self.retryable = retryable
        super().__init__(message)


def _build_session() -> boto3.Session:
    """Build a boto3 Session, using a named profile if set, else the default chain."""
    if settings.aws_profile:
        return boto3.Session(
            region_name=settings.aws_region, profile_name=settings.aws_profile
        )
    return boto3.Session(region_name=settings.aws_region)


@lru_cache()
def _get_client():
    """Bedrock runtime client. Credentials resolve via settings or the default chain."""
    if not settings.aws_region:
        raise BedrockError("AI assistant is not configured (AWS_REGION is missing).")
    # A Bedrock API key authenticates via bearer token; botocore reads it from env.
    if settings.bedrock_api_key:
        os.environ.setdefault("AWS_BEARER_TOKEN_BEDROCK", settings.bedrock_api_key)
    return _build_session().client(
        "bedrock-runtime",
        config=BotoConfig(
            read_timeout=settings.bedrock_timeout_seconds,
            connect_timeout=10,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )


def stream_bedrock(
    system_prompt: str, conversation_history: List[Dict[str, str]]
) -> Generator[str, None, None]:
    """
    Call the Bedrock Converse Stream API for streaming responses.

    Args:
        system_prompt: System instructions, sent as Converse's top-level `system` field.
        conversation_history: [{"role": "user"|"assistant", "content": "..."}] in order,
            ending with the newest user message.

    Yields:
        Text chunks as they arrive from the model.
    """
    if not settings.bedrock_model_id:
        raise BedrockError(
            "AI assistant is not configured (BEDROCK_MODEL_ID is missing)."
        )
    if not conversation_history:
        raise BedrockError("No message to send to the AI assistant.")

    messages = [
        {"role": message["role"], "content": [{"text": message["content"]}]}
        for message in conversation_history
    ]

    inference_config = {"maxTokens": settings.bedrock_max_tokens}
    if settings.bedrock_temperature is not None and _model_supports_temperature(
        settings.bedrock_model_id
    ):
        inference_config["temperature"] = settings.bedrock_temperature

    try:
        response = _get_client().converse_stream(
            modelId=settings.bedrock_model_id,
            system=[{"text": system_prompt}],
            messages=messages,
            inferenceConfig=inference_config,
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        logger.error(f"Bedrock ClientError [{code}]: {str(exc)}")
        if code in _THROTTLING_CODES:
            raise BedrockError(
                "The AI assistant is busy right now. Please try again in a few seconds.",
                retryable=True,
            ) from exc
        if code in _AUTH_CODES:
            raise BedrockError(
                "The AI assistant is unavailable due to a configuration issue."
            ) from exc
        if code in _TIMEOUT_CODES:
            raise BedrockError(
                "The AI assistant took too long to respond. Please try again.",
                retryable=True,
            ) from exc
        if code == "ValidationException":
            raise BedrockError(
                "The request was too large or invalid for the AI assistant."
            ) from exc
        raise BedrockError("The AI assistant could not process that request.") from exc
    except ReadTimeoutError as exc:
        logger.error(f"Bedrock timeout: {str(exc)}")
        raise BedrockError(
            "The AI assistant took too long to respond. Please try again.",
            retryable=True,
        ) from exc
    except BotoCoreError as exc:
        logger.error(f"Bedrock connection error: {str(exc)}", exc_info=True)
        raise BedrockError(
            "Could not reach the AI assistant. Please try again.", retryable=True
        ) from exc

    # Process the streaming response
    stream = response.get("stream")
    if not stream:
        raise BedrockError("The AI assistant returned an empty stream.")

    for event in stream:
        if "contentBlockDelta" in event:
            delta = event["contentBlockDelta"].get("delta", {})
            text = delta.get("text", "")
            if text:
                yield text
        elif "messageStop" in event:
            # Stream complete
            break
        elif "metadata" in event:
            # Contains usage info, we can log it if needed
            pass
