"""Vulnerability Assist Service - AI mitigation & impact generation for a single finding."""

from app.api.llm import complete_llm
from app.api.schemas.chat_schema import VulnAssistRequest
from app.core.logger import get_logger

logger = get_logger(__name__)

MITIGATION_SYSTEM_PROMPT = (
    "You are a security engineer writing mitigation guidance for a vulnerability "
    "tracked in a VAPT (Vulnerability Assessment and Penetration Testing) system.\n\n"
    "Given a description of a vulnerability/problem, write a concise, actionable "
    "mitigation strategy. Use short numbered steps (3-6 steps typical). Be specific "
    "and technical where possible, not generic advice. Do not include any preamble "
    "like 'Here is a mitigation plan' - just output the steps directly."
)

IMPACT_SYSTEM_PROMPT = (
    "You are a security engineer writing an impact assessment for a vulnerability "
    "tracked in a VAPT (Vulnerability Assessment and Penetration Testing) system.\n\n"
    "Given a description of a vulnerability/problem, write a concise impact assessment: "
    "what could realistically happen if this vulnerability is exploited (data exposure, "
    "system compromise, business/compliance consequences, etc). 2-4 sentences, specific "
    "and technical where possible, not generic. Do not include any preamble like "
    "'Here is the impact' - just output the assessment directly."
)

# Bounded output - mitigation steps / impact paragraphs are short by design.
_MAX_TOKENS = 600


def _build_problem(request: VulnAssistRequest) -> str:
    """Compose the free-text problem statement from the finding's context."""
    parts = []
    if request.name:
        parts.append(f"Vulnerability: {request.name}")
    if request.severity:
        parts.append(f"Severity: {request.severity}")
    parts.append(f"Description: {request.description}")
    return "\n".join(parts)


class VulnAssistService:
    """AI generation for a finding's mitigation and impact fields."""

    def generate_mitigation(self, request: VulnAssistRequest) -> str:
        problem = _build_problem(request)
        logger.info("Generating mitigation guidance via LLM")
        return complete_llm(
            MITIGATION_SYSTEM_PROMPT,
            [{"role": "user", "content": problem}],
            max_tokens=_MAX_TOKENS,
        )

    def generate_impact(self, request: VulnAssistRequest) -> str:
        problem = _build_problem(request)
        logger.info("Generating impact assessment via LLM")
        return complete_llm(
            IMPACT_SYSTEM_PROMPT,
            [{"role": "user", "content": problem}],
            max_tokens=_MAX_TOKENS,
        )
