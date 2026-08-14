"""
LLM Gateway - unified interface to LLM providers.

Currently backed by AWS Bedrock. Callers pass a system prompt plus a plain
conversation history and receive streamed text chunks.
"""

import json
import os
from functools import lru_cache
from typing import Callable, Dict, Generator, List, Optional, Tuple

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError, ReadTimeoutError

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Error codes from Bedrock
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------
class LLMError(Exception):
    """Raised when an LLM call cannot be completed. Carries a user-safe message."""

    def __init__(self, message: str, retryable: bool = False):
        self.message = message
        self.retryable = retryable
        super().__init__(message)


# Backwards compatibility alias
BedrockError = LLMError


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _model_supports_temperature(model_id: str) -> bool:
    """Whether the model accepts a `temperature` parameter (Sonnet 5 does not)."""
    lowered = model_id.lower()
    return not any(marker in lowered for marker in _NO_TEMPERATURE_MARKERS)


def _model_has_extended_thinking(model_id: str) -> bool:
    """Sonnet 5 enables extended thinking by default, consuming the token budget."""
    lowered = model_id.lower()
    return any(marker in lowered for marker in _NO_TEMPERATURE_MARKERS)


def _additional_model_fields() -> Dict:
    """Disable extended thinking for models that enable it by default."""
    if _model_has_extended_thinking(settings.bedrock_model_id):
        return {"thinking": {"type": "disabled"}}
    return {}


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
        raise LLMError("AI assistant is not configured (AWS_REGION is missing).")
    # A Bedrock API key authenticates via bearer token; botocore reads it from env.
    if settings.bedrock_api_key:
        os.environ.setdefault("AWS_BEARER_TOKEN_BEDROCK", settings.bedrock_api_key)
    if not settings.bedrock_verify_ssl:
        logger.warning(
            "Bedrock TLS verification is DISABLED (BEDROCK_VERIFY_SSL=false) - "
            "local dev only, never in a deployed environment."
        )
    return _build_session().client(
        "bedrock-runtime",
        verify=settings.bedrock_verify_ssl,
        config=BotoConfig(
            read_timeout=settings.bedrock_timeout_seconds,
            connect_timeout=10,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _build_request(
    system_prompt: str,
    conversation_history: List[Dict[str, str]],
    max_tokens: Optional[int] = None,
) -> Dict:
    """Shared Converse request payload for streaming and non-streaming calls."""
    if not settings.bedrock_model_id:
        raise LLMError("AI assistant is not configured (BEDROCK_MODEL_ID is missing).")
    if not conversation_history:
        raise LLMError("No message to send to the AI assistant.")

    inference_config = {"maxTokens": max_tokens or settings.bedrock_max_tokens}
    if settings.bedrock_temperature is not None and _model_supports_temperature(
        settings.bedrock_model_id
    ):
        inference_config["temperature"] = settings.bedrock_temperature

    request: Dict = {
        "modelId": settings.bedrock_model_id,
        "system": [{"text": system_prompt}],
        "messages": [
            {"role": message["role"], "content": [{"text": message["content"]}]}
            for message in conversation_history
        ],
        "inferenceConfig": inference_config,
    }
    additional = _additional_model_fields()
    if additional:
        request["additionalModelRequestFields"] = additional
    return request


def _raise_for_client_error(exc: ClientError) -> None:
    """Translate a botocore ClientError into a user-safe LLMError."""
    code = exc.response.get("Error", {}).get("Code", "")
    logger.error(f"LLM ClientError [{code}]: {str(exc)}")
    if code in _THROTTLING_CODES:
        raise LLMError(
            "The AI assistant is busy right now. Please try again in a few seconds.",
            retryable=True,
        ) from exc
    if code in _AUTH_CODES:
        raise LLMError(
            "The AI assistant is unavailable due to a configuration issue."
        ) from exc
    if code in _TIMEOUT_CODES:
        raise LLMError(
            "The AI assistant took too long to respond. Please try again.",
            retryable=True,
        ) from exc
    if code == "ValidationException":
        raise LLMError(
            "The request was too large or invalid for the AI assistant."
        ) from exc
    raise LLMError("The AI assistant could not process that request.") from exc


def complete_llm(
    system_prompt: str,
    conversation_history: List[Dict[str, str]],
    max_tokens: Optional[int] = None,
) -> str:
    """
    Single-shot (non-streaming) LLM completion.

    Args:
        system_prompt: System instructions for the model.
        conversation_history: [{"role": ..., "content": ...}] ending with the user message.
        max_tokens: Hard ceiling on the generated length. Falls back to the global default.

    Returns:
        The assistant's reply text.

    Raises:
        LLMError: If the LLM call fails or returns nothing.
    """
    request = _build_request(system_prompt, conversation_history, max_tokens)

    try:
        response = _get_client().converse(**request)
    except ClientError as exc:
        _raise_for_client_error(exc)
    except ReadTimeoutError as exc:
        logger.error(f"LLM timeout: {str(exc)}")
        raise LLMError(
            "The AI assistant took too long to respond. Please try again.",
            retryable=True,
        ) from exc
    except BotoCoreError as exc:
        logger.error(f"LLM connection error: {str(exc)}", exc_info=True)
        raise LLMError(
            "Could not reach the AI assistant. Please try again.", retryable=True
        ) from exc

    content_blocks = response.get("output", {}).get("message", {}).get("content", [])
    reply = "".join(block.get("text", "") for block in content_blocks).strip()
    if not reply:
        raise LLMError("The AI assistant returned an empty response.")
    return reply


def stream_llm(
    system_prompt: str, conversation_history: List[Dict[str, str]]
) -> Generator[str, None, None]:
    """
    Stream a response from the LLM.

    Args:
        system_prompt: System instructions for the model.
        conversation_history: [{"role": "user"|"assistant", "content": "..."}] in order,
            ending with the newest user message.

    Yields:
        Text chunks as they arrive from the model.

    Raises:
        LLMError: If the LLM call fails.
    """
    request = _build_request(system_prompt, conversation_history)

    try:
        response = _get_client().converse_stream(**request)
    except ClientError as exc:
        _raise_for_client_error(exc)
    except ReadTimeoutError as exc:
        logger.error(f"LLM timeout: {str(exc)}")
        raise LLMError(
            "The AI assistant took too long to respond. Please try again.",
            retryable=True,
        ) from exc
    except BotoCoreError as exc:
        logger.error(f"LLM connection error: {str(exc)}", exc_info=True)
        raise LLMError(
            "Could not reach the AI assistant. Please try again.", retryable=True
        ) from exc

    # Process the streaming response
    stream = response.get("stream")
    if not stream:
        raise LLMError("The AI assistant returned an empty stream.")

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


ToolHandler = Callable[[str, dict], dict]


def converse_with_tools(
    system_prompt: str,
    conversation_history: List[Dict[str, str]],
    tool_config: Dict,
    tool_handler: ToolHandler,
    max_tokens: Optional[int] = None,
    max_tool_rounds: int = 5,
) -> Tuple[str, List[Dict]]:
    """
    Non-streaming LLM call with a tool-calling loop.

    Returns:
        (reply_text, visualizations) where visualizations is a list of
        render_visualization tool inputs emitted during the conversation.
    """
    from app.api.llm.tools import VISUALIZATION_TOOL_NAME

    if not settings.bedrock_model_id:
        raise LLMError("AI assistant is not configured (BEDROCK_MODEL_ID is missing).")
    if not conversation_history:
        raise LLMError("No message to send to the AI assistant.")

    inference_config: Dict = {"maxTokens": max_tokens or settings.bedrock_max_tokens}
    if settings.bedrock_temperature is not None and _model_supports_temperature(
        settings.bedrock_model_id
    ):
        inference_config["temperature"] = settings.bedrock_temperature

    messages = [
        {"role": m["role"], "content": [{"text": m["content"]}]}
        for m in conversation_history
    ]

    visualizations: List[Dict] = []
    client = _get_client()

    for round_num in range(max_tool_rounds):
        converse_kwargs: Dict = {
            "modelId": settings.bedrock_model_id,
            "system": [{"text": system_prompt}],
            "messages": messages,
            "toolConfig": tool_config,
            "inferenceConfig": inference_config,
        }
        additional = _additional_model_fields()
        if additional:
            converse_kwargs["additionalModelRequestFields"] = additional

        try:
            response = client.converse(**converse_kwargs)
        except ClientError as exc:
            _raise_for_client_error(exc)
        except ReadTimeoutError as exc:
            logger.error(f"LLM timeout (tool round {round_num}): {exc}")
            raise LLMError(
                "The AI assistant took too long to respond. Please try again.",
                retryable=True,
            ) from exc
        except BotoCoreError as exc:
            logger.error(
                f"LLM connection error (tool round {round_num}): {exc}",
                exc_info=True,
            )
            raise LLMError(
                "Could not reach the AI assistant. Please try again.",
                retryable=True,
            ) from exc

        assistant_msg = response["output"]["message"]
        messages.append(assistant_msg)

        if response.get("stopReason", "end_turn") != "tool_use":
            text_parts = [b["text"] for b in assistant_msg["content"] if "text" in b]
            return "".join(text_parts).strip(), visualizations

        tool_results = []
        for block in assistant_msg["content"]:
            if "toolUse" not in block:
                continue
            tu = block["toolUse"]
            tool_id = tu["toolUseId"]
            tool_name = tu["name"]
            tool_input = tu["input"]

            logger.info(
                f"Tool call: {tool_name}({json.dumps(tool_input, default=str)[:200]})"
            )

            if tool_name == VISUALIZATION_TOOL_NAME:
                visualizations.append(tool_input)

            try:
                result = tool_handler(tool_name, tool_input)
                # Bedrock requires toolResult.content[].json to be a JSON object, not a bare array.
                result_obj = result if isinstance(result, dict) else {"result": result}
                tool_results.append(
                    {
                        "toolResult": {
                            "toolUseId": tool_id,
                            "content": [{"json": result_obj}],
                            "status": "success",
                        }
                    }
                )
            except Exception as exc:
                logger.warning(f"Tool {tool_name} failed: {exc}")
                tool_results.append(
                    {
                        "toolResult": {
                            "toolUseId": tool_id,
                            "content": [{"text": str(exc)}],
                            "status": "error",
                        }
                    }
                )

        messages.append({"role": "user", "content": tool_results})

    logger.warning(f"Tool loop hit max rounds ({max_tool_rounds})")
    return (
        "I wasn't able to complete the analysis. Please try rephrasing your question.",
        visualizations,
    )


# Backwards compatibility alias
stream_bedrock = stream_llm
