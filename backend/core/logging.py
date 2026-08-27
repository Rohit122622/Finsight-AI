"""
Structured logging and secret sanitization for FinSentry AI.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

                                                                   
SENSITIVE_PATTERNS = [
    re.compile(r"(password|passwd|pwd)", re.IGNORECASE),
    re.compile(r"(access_token|refresh_token|token|jwt|bearer)", re.IGNORECASE),
    re.compile(r"(client_secret|secret|secret_key|api_key|access_key)", re.IGNORECASE),
    re.compile(r"(code|authorization_code|oauth_state)", re.IGNORECASE),
    re.compile(r"(mongodb_uri|redis_password|database_password)", re.IGNORECASE),
]

                                                        
JWT_PATTERN = re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}")
                                  
BEARER_PATTERN = re.compile(r"Bearer\s+[a-zA-Z0-9._~+/-]+=*", re.IGNORECASE)


def sanitize_value(key: str, value: Any) -> Any:
    """Recursively redact sensitive values based on key names or patterns."""
    if value is None:
        return None

                                               
    for pat in SENSITIVE_PATTERNS:
        if pat.search(key):
            return "[REDACTED]"

    if isinstance(value, str):
                                               
        sanitized = JWT_PATTERN.sub("[REDACTED_JWT]", value)
        sanitized = BEARER_PATTERN.sub("Bearer [REDACTED]", sanitized)
        return sanitized

    if isinstance(value, dict):
        return {k: sanitize_value(k, v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [sanitize_value(key, item) for item in value]

    return value


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize all key-value pairs in a dictionary."""
    if not isinstance(data, dict):
        return {}
    return {k: sanitize_value(k, v) for k, v in data.items()}


class StructuredLogFormatter(logging.Formatter):
    """Formats log records as structured JSON with automatic secret redaction."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize_value("message", record.getMessage()),
        }

                                                               
        for attr in (
            "job_id",
            "agent_name",
            "task_type",
            "document_id",
            "user_id",
            "session_id",
            "started_at",
            "completed_at",
            "status",
            "latency",
            "latency_ms",
            "model",
            "retry_count",
            "error",
            "worker_id",
        ):
            val = getattr(record, attr, None)
            if val is not None:
                log_payload[attr] = sanitize_value(attr, val)

        if record.exc_info:
            log_payload["exception"] = sanitize_value(
                "exception", self.formatException(record.exc_info)
            )

        return json.dumps(log_payload)


def get_agent_logger(name: str = "finsentry.agent") -> logging.Logger:
    """Return a logger configured for structured agent logging."""
    return logging.getLogger(name)


def log_agent_event(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    job_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    task_type: Optional[str] = None,
    document_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    started_at: Optional[str] = None,
    completed_at: Optional[str] = None,
    status: Optional[str] = None,
    latency: Optional[float] = None,
    latency_ms: Optional[float] = None,
    model: Optional[str] = None,
    retry_count: Optional[int] = None,
    error: Optional[str] = None,
    worker_id: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Emit a structured log event with automatic secret sanitization.
    """
    extra: Dict[str, Any] = {}
    if job_id is not None:
        extra["job_id"] = job_id
    if agent_name is not None:
        extra["agent_name"] = agent_name
    if task_type is not None:
        extra["task_type"] = task_type
    if document_id is not None:
        extra["document_id"] = document_id
    if user_id is not None:
        extra["user_id"] = user_id
    if session_id is not None:
        extra["session_id"] = session_id
    if started_at is not None:
        extra["started_at"] = started_at
    if completed_at is not None:
        extra["completed_at"] = completed_at
    if status is not None:
        extra["status"] = status
    if latency is not None:
        extra["latency"] = latency
    if latency_ms is not None:
        extra["latency_ms"] = latency_ms
        if latency is None:
            extra["latency"] = latency_ms / 1000.0
    if model is not None:
        extra["model"] = model
    if retry_count is not None:
        extra["retry_count"] = retry_count
    if error is not None:
        extra["error"] = error
    if worker_id is not None:
        extra["worker_id"] = worker_id

    if extra_data:
        sanitized_extra = sanitize_dict(extra_data)
        extra.update(sanitized_extra)

    logger.log(level, message, extra=extra)
