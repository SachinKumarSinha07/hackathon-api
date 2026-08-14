"""Chat Service - builds vulnerability-scoped prompts and talks to the LLM gateway"""

import json
import time
from datetime import date
from sqlalchemy.orm import Session
from typing import Dict, Generator, List, Optional

from app.api.models.vulnerability_master import VulnerabilityMaster
from app.api.repositories.vulnerability_repository import (
    VulnerabilityRepository,
    is_filter_unset,
)
from app.api.schemas.chat_schema import ChatRequest
from app.api.schemas.vulnerability_schema import VulnerabilityFilterParams
from app.api.llm import converse_with_tools
from app.api.llm.tools import (
    CHAT_TOOL_CONFIG,
    VISUALIZATION_TOOL_NAME,
    aggregate_records,
)
from app.core.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Session storage with automatic cleanup
# ---------------------------------------------------------------------------
class SessionData:
    """Holds conversation history and metadata for a session."""

    def __init__(self):
        self.history: List[Dict[str, str]] = []
        self.last_used_at: float = time.time()

    def touch(self):
        """Update last used timestamp."""
        self.last_used_at = time.time()


# In-memory session store: resets on server restart and is NOT safe across
# multiple instances. Placeholder for a real session store (Redis/DB) later.
_SESSIONS: Dict[str, SessionData] = {}

# Sessions not touched within this window are eligible for cleanup (1 hour)
SESSION_EXPIRY_SECONDS = 3600

# Keep the prompt bounded - only the most recent messages are replayed.
MAX_HISTORY_MESSAGES = 20


# ---------------------------------------------------------------------------
# Rate limiting (10 requests per minute per session)
# ---------------------------------------------------------------------------
class RateLimiter:
    """Simple in-memory rate limiter per session."""

    MAX_REQUESTS = 10
    WINDOW_SECONDS = 60

    def __init__(self):
        # session_id -> list of request timestamps
        self._requests: Dict[str, List[float]] = {}

    def is_allowed(self, session_id: str) -> bool:
        """Check if the session is within rate limits."""
        now = time.time()
        cutoff = now - self.WINDOW_SECONDS

        # Get or create request history for this session
        timestamps = self._requests.get(session_id, [])
        # Remove timestamps outside the window
        timestamps = [ts for ts in timestamps if ts > cutoff]

        if len(timestamps) >= self.MAX_REQUESTS:
            self._requests[session_id] = timestamps
            return False

        timestamps.append(now)
        self._requests[session_id] = timestamps
        return True

    def cleanup_old_entries(self):
        """Remove entries for sessions with no recent requests."""
        now = time.time()
        cutoff = now - self.WINDOW_SECONDS * 2
        to_delete = [
            sid
            for sid, timestamps in self._requests.items()
            if not timestamps or max(timestamps) < cutoff
        ]
        for sid in to_delete:
            del self._requests[sid]


_RATE_LIMITER = RateLimiter()


def _get_session(session_id: str) -> SessionData:
    """Get or create session data, cleaning up stale sessions periodically."""
    _cleanup_stale_sessions()

    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = SessionData()

    session = _SESSIONS[session_id]
    session.touch()
    return session


def _cleanup_stale_sessions():
    """Remove sessions that haven't been used within the expiry window."""
    now = time.time()
    cutoff = now - SESSION_EXPIRY_SECONDS
    stale = [sid for sid, data in _SESSIONS.items() if data.last_used_at < cutoff]
    for sid in stale:
        logger.debug(f"Cleaning up stale session: {sid}")
        del _SESSIONS[sid]

    # Also clean up rate limiter entries
    _RATE_LIMITER.cleanup_old_entries()


class RateLimitExceeded(Exception):
    """Raised when a session exceeds the rate limit."""

    pass


SYSTEM_ROLE = "You are a security operations assistant for a VAPT tracker."

ANSWER_RULES = (
    "Answer using ONLY the vulnerability data provided below. "
    "Do not use outside knowledge about these findings and never guess or invent records. "
    "If the data does not cover what was asked, say so plainly. "
    "When counting or grouping, count only the records provided. "
    "Keep answers concise and reference the data scope naturally when it is relevant."
)

TOOL_INSTRUCTIONS = (
    "You have tools for data aggregation and visualization.\n"
    "NEVER write a markdown table (pipe characters `|`) in your text reply - the chat UI "
    "cannot render markdown tables and they will show up as broken text. Use the "
    "render_visualization tool instead any time the answer involves 2 or more records "
    "with multiple fields (e.g. listing vulnerabilities with their owner, status, dates, etc.).\n"
    "Rules:\n"
    "1. Grouped counts / breakdowns / comparisons -> call aggregate_vulnerabilities, then "
    "call render_visualization (type 'bar' or 'pie') with the result.\n"
    "2. Listing multiple specific records with several fields each (e.g. 'list critical "
    "vulnerabilities', 'show overdue items') -> call render_visualization directly with "
    "type 'table', where each item in data is one object with the relevant fields as keys "
    "(e.g. name, pic, status, target_date). Do not aggregate first.\n"
    "3. After any render_visualization call, follow with a brief text commentary - do not "
    "repeat the tabular data as text.\n"
    "4. For a single number or a single record, answer directly from the data without tools."
)

FILTER_LABELS = {
    "project": "Project",
    "round": "Round",
    "severity": "Severity",
    "dev_status": "Status",
}


class ChatService:
    """Service for vulnerability Q&A chat"""

    def __init__(self, db: Session):
        self.db = db
        self.repository = VulnerabilityRepository(db)

    def chat(
        self, request: ChatRequest, allowed_project_ids: Optional[List[int]] = None
    ) -> Generator[str, None, None]:
        """
        Stream chat response - yields SSE-formatted chunks as the LLM generates them.

        Yields:
            SSE-formatted strings: "data: {json}\n\n"
        """
        # Rate limiting check
        if not _RATE_LIMITER.is_allowed(request.session_id):
            raise RateLimitExceeded(
                f"Rate limit exceeded for session {request.session_id}. "
                f"Max {RateLimiter.MAX_REQUESTS} requests per {RateLimiter.WINDOW_SECONDS} seconds."
            )

        is_global = request.scope == "global"
        filters = None if is_global else request.filters
        active_filters = self._active_filters(filters)

        records = self.repository.get_vulnerabilities(
            filters=filters, allowed_project_ids=allowed_project_ids
        )
        logger.info(
            f"Chat request - session: {request.session_id}, scope: {request.scope}, "
            f"records: {len(records)}, filters: {active_filters}"
        )

        system_prompt = self._build_system_prompt(records, is_global, active_filters)

        session = _get_session(request.session_id)
        messages = session.history[-MAX_HISTORY_MESSAGES:] + [
            {"role": "user", "content": request.message}
        ]

        tool_handler = self._make_tool_handler(records)

        reply_text, visualizations = converse_with_tools(
            system_prompt, messages, CHAT_TOOL_CONFIG, tool_handler
        )

        # Emit visualization events before text so charts render first
        for vis in visualizations:
            yield f"data: {json.dumps({'visualization': vis})}\n\n"

        # Emit text in small chunks for a streaming feel
        if reply_text:
            words = reply_text.split(" ")
            for i in range(0, len(words), 4):
                chunk = " ".join(words[i : i + 4])
                if i + 4 < len(words):
                    chunk += " "
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"

        # Update conversation history
        session.history.append({"role": "user", "content": request.message})
        session.history.append({"role": "assistant", "content": reply_text})
        session.history = session.history[-MAX_HISTORY_MESSAGES:]

    @staticmethod
    def _active_filters(filters: Optional[VulnerabilityFilterParams]) -> Dict[str, str]:
        """Filters that actually constrain the data, keyed by display label."""
        if filters is None:
            return {}
        return {
            label: getattr(filters, field).strip()
            for field, label in FILTER_LABELS.items()
            if not is_filter_unset(getattr(filters, field))
        }

    @staticmethod
    def _make_tool_handler(records: List[VulnerabilityMaster]):
        def handler(tool_name: str, tool_input: dict) -> dict:
            if tool_name == "aggregate_vulnerabilities":
                return aggregate_records(records, tool_input["group_by"])
            if tool_name == VISUALIZATION_TOOL_NAME:
                return {"status": "rendered", "message": "Chart displayed to user"}
            return {"error": f"Unknown tool: {tool_name}"}

        return handler

    @staticmethod
    def _format_records(records: List[VulnerabilityMaster]) -> str:
        """Compact JSON array of the fields the assistant is allowed to reason over."""
        return json.dumps(
            [
                {
                    "name": record.vulnerability_name,
                    "severity": record.severity,
                    "component_url": record.endpoint_url_list,
                    "pic": record.pic,
                    "target_date": record.target_date.isoformat()
                    if record.target_date
                    else None,
                    "status": record.status,
                }
                for record in records
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _build_system_prompt(
        self,
        records: List[VulnerabilityMaster],
        is_global: bool,
        active_filters: Dict[str, str],
    ) -> str:
        if is_global:
            scope_line = (
                "The data below is the FULL vulnerability dataset the user is permitted to see "
                "(no table filters applied)."
            )
        elif active_filters:
            filter_text = ", ".join(
                f"{label}: {value}" for label, value in active_filters.items()
            )
            scope_line = (
                "The data below is a FILTERED view of the vulnerability table. "
                f"Active filters - {filter_text}. "
                "Make it clear that your answer covers only this filtered view."
            )
        else:
            scope_line = "The data below is the vulnerability table view with no filters currently active."

        return (
            f"{SYSTEM_ROLE}\n\n"
            f"{ANSWER_RULES}\n\n"
            f"{TOOL_INSTRUCTIONS}\n\n"
            f"{scope_line}\n"
            f"Today's date is {date.today().isoformat()} (use it for overdue/aging questions).\n"
            f"Record count: {len(records)}\n\n"
            f"VULNERABILITY DATA (JSON array):\n{self._format_records(records)}"
        )
