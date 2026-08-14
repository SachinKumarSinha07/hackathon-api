"""Dashboard Service - generates the leadership executive summary from dashboard metrics."""

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from app.api.llm import complete_llm
from app.api.schemas.dashboard_schema import (
    DashboardMetrics,
    ExportSummaryRequest,
    ExportSummaryResponse,
)
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

SUMMARY_SYSTEM_PROMPT = (
    "You are a senior security analyst writing a one-page executive summary of VAPT "
    "(Vulnerability Assessment and Penetration Testing) results, for an audience that "
    "includes both security-technical readers and non-technical leadership (CFO, CEO, "
    "board members).\n\n"
    "USE PRECISE SECURITY LANGUAGE — do not water it down. Use real terms like severity "
    "tier, SLA breach, remediation velocity, attack surface, risk exposure, recurring/"
    "regressed finding, and mean time to remediate where they fit. \n\n "
    "GROUND EVERY CLAIM IN THE PROVIDED JSON. Never invent, round loosely, or imply a "
    "statistic that isn't directly supported by the input data. If a metric isn't present "
    "in the JSON, do not reference it.\n\n"
    "FORMAT AS STRUCTURED MARKDOWN, not flowing prose. Use this EXACT structure, with the "
    "section headings written exactly as shown (each on its own line, prefixed with '## ') "
    "and bullet points prefixed with '- ':\n\n"
    "## Risk Posture\n"
    "One or two sentences stating the overall security posture directly, using "
    "severityBreakdown.total and the critical/high proportion. Do not hedge with vague "
    "phrases like 'several issues were found.'\n\n"
    "## Key Numbers\n"
    "- One bullet per severity tier from severityBreakdown (exact counts).\n"
    "- One or more bullets citing the SLA breach rate from slaComplianceBySeverity "
    "(breached vs onTime, by severity tier), with exact figures.\n\n"
    "## Trend\n"
    "One to two sentences stating whether remediation is improving or worsening, using "
    "vulnerabilityAging (are findings aging out / stacking up in older buckets) and "
    "repeatFindingsTrend (is 'reopened' or 'recurring' rising or falling period over "
    "period). Name the direction explicitly (improving, worsening, or flat).\n\n"
    "## Top Concern\n"
    "One to two sentences identifying the single most urgent issue: the highest-severity "
    "SLA breach, the fastest-growing escalation category (escalationDistribution), or the "
    "most significant repeat/regressed finding. Pick one, not a list.\n\n"
    "## Recommendation\n"
    "- Three or four bullets with concrete, specific next actions tied directly to the top "
    "concern identified above — not generic advice like 'improve security posture.'\n\n"
    "Do not add any other headings, do not add an intro or conclusion outside this "
    "structure, and do not use any markdown other than '## ' headings and '- ' bullets "
    "(no bold, no tables, no numbered lists).\n\n"
    "Write with the authority of an analyst briefing leadership, not a marketing summary. "
    "Every sentence or bullet should carry a specific fact from the data. The full output "
    "(including headings and bullets) must stay within 1800-2400 characters — do not "
    "truncate mid-sentence; write tightly enough to finish cleanly within it."
)

# Second enforcement of the limit lives in the prompt above; this is the hard ceiling.
MAX_SUMMARY_CHARS = 2400

# Cached summaries keyed by the input hash. In-memory only: resets on restart and is
# NOT shared across instances. Placeholder for Redis if this needs to scale out.
_SUMMARY_CACHE: Dict[str, Tuple[str, str, float]] = {}
CACHE_TTL_SECONDS = 3600


def _canonical_hash(metrics: DashboardMetrics) -> str:
    """Stable SHA-256 over the metric payload; key order does not affect the digest."""
    canonical = json.dumps(
        metrics.model_dump(by_alias=True), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _get_cached(input_hash: str) -> Optional[Tuple[str, str]]:
    """Return (summary_text, generated_at) when a fresh entry exists."""
    entry = _SUMMARY_CACHE.get(input_hash)
    if not entry:
        return None

    summary_text, generated_at, stored_at = entry
    if time.time() - stored_at > CACHE_TTL_SECONDS:
        del _SUMMARY_CACHE[input_hash]
        return None
    return summary_text, generated_at


def _evict_expired() -> None:
    cutoff = time.time() - CACHE_TTL_SECONDS
    for key in [k for k, (_, _, ts) in _SUMMARY_CACHE.items() if ts < cutoff]:
        del _SUMMARY_CACHE[key]


class DashboardService:
    """Service for dashboard-level AI features."""

    def export_summary(self, request: ExportSummaryRequest) -> ExportSummaryResponse:
        """Generate (or replay a cached) executive summary for the given metrics."""
        _evict_expired()

        input_hash = _canonical_hash(request.metrics)
        cached = _get_cached(input_hash)

        if cached:
            summary_text, generated_at = cached
            # Audit trail: hash + timestamp + length only, never the summary body.
            logger.info(
                f"Executive summary served from cache - hash: {input_hash[:16]}, "
                f"at: {datetime.now(timezone.utc).isoformat()}, chars: {len(summary_text)}"
            )
            return ExportSummaryResponse(
                summary_text=summary_text, generated_at=generated_at, cached=True
            )

        user_message = self._build_user_message(request)

        summary_text = complete_llm(
            SUMMARY_SYSTEM_PROMPT,
            [{"role": "user", "content": user_message}],
            max_tokens=settings.bedrock_summary_max_tokens,
        )
        summary_text = self._enforce_char_limit(summary_text)

        generated_at = datetime.now(timezone.utc).isoformat()
        _SUMMARY_CACHE[input_hash] = (summary_text, generated_at, time.time())

        # Audit trail: hash + timestamp + length only, never the summary body.
        logger.info(
            f"Executive summary generated - hash: {input_hash[:16]}, "
            f"at: {generated_at}, chars: {len(summary_text)}"
        )

        return ExportSummaryResponse(
            summary_text=summary_text, generated_at=generated_at, cached=False
        )

    @staticmethod
    def _build_user_message(request: ExportSummaryRequest) -> str:
        payload = json.dumps(
            request.metrics.model_dump(by_alias=True),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        scope = request.scope_label or "All projects"
        return f"Reporting scope: {scope}\n\nDASHBOARD METRICS (JSON):\n{payload}"

    @staticmethod
    def _enforce_char_limit(text: str) -> str:
        """Trim at a sentence boundary if the model overshot the character budget."""
        text = text.strip()
        if len(text) <= MAX_SUMMARY_CHARS:
            return text

        truncated = text[:MAX_SUMMARY_CHARS]
        last_stop = truncated.rfind(". ")
        return (truncated[: last_stop + 1] if last_stop > 0 else truncated).strip()
