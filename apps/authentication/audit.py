import logging

logger = logging.getLogger("security.audit")


def log_auth_event(
    *,
    request,
    action: str,
    success: bool,
    user=None,
    reason: str = ""
):
    logger.warning(
        "AUTH_EVENT",
        extra={
            "action": action,
            "success": success,
            "user_id": getattr(user, "id", None),
            "email": getattr(user, "email", None),
            "ip": request.META.get("REMOTE_ADDR"),
            "user_agent": request.META.get("HTTP_USER_AGENT"),
            "reason": reason,
        }
    )
