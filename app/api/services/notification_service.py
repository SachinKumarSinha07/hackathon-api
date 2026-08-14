"""Notification Service - Thin wrapper around the SES EmailGateway.

Keeps the email/SES concerns isolated from the business services. The
underlying gateway (email_gateway.py at the project root) loads templates from
the templates/ folder and sends via Amazon SES.

Email delivery is treated as best-effort: failures are logged but never raised
to the caller, so a transient SES/config issue can't roll back or fail the
primary business operation (e.g. registering a risk acceptance).
"""

from typing import Dict, List, Optional

from app.core.logger import get_logger

logger = get_logger(__name__)


class NotificationService:
    """Sends templated notification emails without breaking the caller's flow."""

    def send_template(
        self,
        template_name: str,
        to_addresses: List[str],
        context: Dict,
        cc_addresses: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Render and send a templated email. Returns the SES MessageId on success,
        or None if the email could not be sent (misconfiguration, SES error, ...).

        Never raises: any failure is logged and swallowed so the primary
        operation is unaffected.
        """
        if not to_addresses:
            logger.warning(
                f"No recipients resolved for template '{template_name}'; skipping email send."
            )
            return None

        try:
            # Imported lazily so the app can boot even when boto3/SES config is
            # absent; only sending a notification requires it.
            from email_gateway import EmailGateway, EmailGatewayError
        except Exception as e:  # pragma: no cover - import/env issues
            logger.error(f"Email gateway unavailable, skipping '{template_name}' email: {e}")
            return None

        try:
            gateway = EmailGateway()
            message_id = gateway.send_template(
                template_name=template_name,
                to_addresses=to_addresses,
                context=context,
                cc_addresses=cc_addresses,
            )
            logger.info(
                f"Notification email '{template_name}' sent to {to_addresses} "
                f"(cc={cc_addresses or []}) | MessageId: {message_id}"
            )
            return message_id
        except EmailGatewayError as e:
            logger.error(f"Failed to send '{template_name}' email to {to_addresses}: {e}")
            return None
        except Exception as e:  # pragma: no cover - unexpected runtime errors
            logger.error(
                f"Unexpected error sending '{template_name}' email to {to_addresses}: {e}",
                exc_info=True,
            )
            return None
