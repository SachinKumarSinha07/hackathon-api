"""Chat Controller - AI assistant endpoint scoped to vulnerability data"""

import json
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import get_db
from app.api.schemas.chat_schema import (
    ChatRequest,
    VulnAssistRequest,
    VulnAssistResponse,
)
from app.api.llm import LLMError
from app.api.services.chat_service import ChatService, RateLimitExceeded
from app.api.services.vuln_assist_service import VulnAssistService
from app.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


# ---------------------------------------------------------------------------
# TODO: Replace this placeholder with real authentication.
# When auth is implemented, this should extract allowed_project_ids from the
# authenticated user's session/token (e.g., via a JWT claim or DB lookup).
# For now, we accept project_ids as an optional query parameter for local testing.
# ---------------------------------------------------------------------------
def get_allowed_project_ids(
    project_ids: Optional[List[int]] = Query(
        None,
        description="Project IDs the user is allowed to access (placeholder for auth)",
    ),
) -> Optional[List[int]]:
    """
    Dependency that provides the list of project IDs the user can access.

    **SECURITY WARNING**: This is a placeholder. In production, this MUST
    derive from the authenticated user's permissions, NOT from request params.
    """
    return project_ids


@router.post(
    "",
    status_code=status.HTTP_200_OK,
    summary="Ask the AI assistant about vulnerability data (streaming)",
    description="""
    Answers questions about vulnerability data using an LLM (AWS Bedrock).
    Returns Server-Sent Events (SSE) as the LLM generates its response.

    **Event Format:**
    - Progress events: `data: {"chunk": "partial text"}`
    - Completion event: `data: {"done": true}`
    - Error events: `data: {"error": "message", "code": 429|502|503}`

    **Scope:**
    - `global`: the assistant receives every vulnerability the caller is permitted to see,
      ignoring the table filters.
    - `filtered`: the assistant receives only the records matching the active table filters
      (Project, Round, Severity, Dev Status).

    Pagination is never applied - the complete matching set is sent to the model.
    Conversation history is kept per `sessionId`.

    **Rate Limiting:** Max 10 requests per minute per session.
    """,
    responses={
        200: {
            "description": "SSE stream of chat response chunks",
            "content": {"text/event-stream": {}},
        }
    },
)
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    allowed_project_ids: Optional[List[int]] = Depends(get_allowed_project_ids),
):
    """Chat over vulnerability data (streaming SSE response)"""
    service = ChatService(db)

    def generate():
        try:
            for chunk in service.chat(request, allowed_project_ids=allowed_project_ids):
                yield chunk
        except RateLimitExceeded as exc:
            logger.warning(f"Rate limit exceeded for session {request.session_id}")
            yield f"data: {json.dumps({'error': str(exc), 'code': 429})}\n\n"
        except LLMError as exc:
            logger.warning(
                f"Chat unavailable for session {request.session_id}: {exc.message}"
            )
            error_code = 503 if exc.retryable else 502
            yield f"data: {json.dumps({'error': exc.message, 'code': error_code})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


def _assist_error(exc: LLMError) -> HTTPException:
    """Map an LLMError to the same status codes the chat stream uses."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        if exc.retryable
        else status.HTTP_502_BAD_GATEWAY,
        detail=exc.message,
    )


@router.post(
    "/mitigation",
    response_model=VulnAssistResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate AI mitigation guidance for a single finding",
    description=(
        "Returns an AI-generated mitigation strategy (numbered steps) for the given "
        "vulnerability description. Non-streaming. Intended to fill/override the "
        "mitigation field in the edit form when the user clicks 'Ask AI'."
    ),
)
def generate_mitigation(request: VulnAssistRequest):
    """Generate mitigation guidance for a finding."""
    try:
        text = VulnAssistService().generate_mitigation(request)
    except LLMError as exc:
        logger.warning(f"Mitigation generation unavailable: {exc.message}")
        raise _assist_error(exc)
    return VulnAssistResponse(text=text)


@router.post(
    "/impact",
    response_model=VulnAssistResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate AI impact assessment for a single finding",
    description=(
        "Returns an AI-generated impact assessment for the given vulnerability "
        "description. Non-streaming. Intended to fill/override the impact field in "
        "the edit form when the user clicks 'Ask AI'."
    ),
)
def generate_impact(request: VulnAssistRequest):
    """Generate an impact assessment for a finding."""
    try:
        text = VulnAssistService().generate_impact(request)
    except LLMError as exc:
        logger.warning(f"Impact generation unavailable: {exc.message}")
        raise _assist_error(exc)
    return VulnAssistResponse(text=text)
