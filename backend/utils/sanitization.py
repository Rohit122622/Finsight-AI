"""
FinSentry AI — Secret Sanitization & Redaction Utilities.

Provides recursive sanitization for:
- API Keys (OpenAI, Anthropic, Groq, Google, LangSmith, generic)
- JWTs & Bearer Tokens
- Passwords & Auth Headers
- MongoDB / Redis / Database Connection Strings with Credentials
- Cloudflare R2 / AWS Credentials
- Nested Dictionaries, Lists, and Primitive Data Structures
"""

import re
from typing import Any, Dict, List, Set, Union

SECRET_PATTERNS = [
                                          
    (r"\beyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b", "[REDACTED_JWT]"),
                                         
    (r"(?i)(bearer\s+)[a-zA-Z0-9_\-\.]{10,}", r"\1[REDACTED_TOKEN]"),
                     
    (r"sk-[a-zA-Z0-9_\-]{20,}", "[REDACTED_OPENAI_KEY]"),
                   
    (r"gsk_[a-zA-Z0-9_\-]{20,}", "[REDACTED_GROQ_KEY]"),
                          
    (r"AIzaSy[a-zA-Z0-9_\-]{30,}", "[REDACTED_GOOGLE_KEY]"),
                        
    (r"ant-[a-zA-Z0-9_\-]{20,}", "[REDACTED_ANTHROPIC_KEY]"),
                        
    (r"lsv2_[a-zA-Z0-9_\-]{20,}", "[REDACTED_LANGSMITH_KEY]"),
                                 
    (r"(?i)(api[_\-]?key[\s:=]+)['\"]?[a-zA-Z0-9_\-\.]{8,}['\"]?", r"api_key=[REDACTED_KEY]"),
                          
    (r"(?i)(password[\s:=]+)['\"]?[^'\"\s,;]+['\"]?", r"password=[REDACTED]"),
                                                               
    (r"mongodb(?:\+srv)?:\/\/[^:]+:[^@]+@", "mongodb://[REDACTED_USER]:[REDACTED_PASS]@"),
                                                    
    (r"redis:\/\/(?::[^@]+@|[^:]+:[^@]+@)", "redis://:[REDACTED_AUTH]@"),
                                
    (r"(?i)(secret_access_key[\s:=]+)['\"]?[a-zA-Z0-9_\-\.]{16,}['\"]?", r"secret_access_key=[REDACTED]"),
    (r"(?i)(access_key_id[\s:=]+)['\"]?[a-zA-Z0-9_\-\.]{16,}['\"]?", r"access_key_id=[REDACTED]"),
]

SENSITIVE_FIELD_NAMES: Set[str] = {
    "password",
    "jwt_secret_key",
    "secret_key",
    "access_token",
    "refresh_token",
    "token",
    "authorization",
    "auth_header",
    "api_key",
    "groq_api_key",
    "google_api_key",
    "openai_api_key",
    "anthropic_api_key",
    "langsmith_api_key",
    "r2_secret_access_key",
    "r2_access_key_id",
    "redis_password",
    "redis_url",
    "celery_broker_url",
    "celery_result_backend",
    "mongodb_uri",
}


def sanitize_text(text: str) -> str:
    """Scrub known secrets and credentials from a text string."""
    if not text:
        return ""
    sanitized = str(text)
    for pattern, replacement in SECRET_PATTERNS:
        sanitized = re.sub(pattern, replacement, sanitized)
    return sanitized


def sanitize_data(data: Any) -> Any:
    """
    Recursively sanitize any Python object (dict, list, tuple, set, str, primitive)
    to guarantee zero secret leakage in logs, traces, or stored telemetry.
    """
    if data is None:
        return None
    if isinstance(data, str):
        return sanitize_text(data)
    if isinstance(data, (int, float, bool)):
        return data
    if isinstance(data, dict):
        sanitized_dict: Dict[str, Any] = {}
        for k, v in data.items():
            key_str = str(k).lower()
            if any(sens in key_str for sens in SENSITIVE_FIELD_NAMES):
                sanitized_dict[k] = "[REDACTED]"
            else:
                sanitized_dict[k] = sanitize_data(v)
        return sanitized_dict
    if isinstance(data, list):
        return [sanitize_data(item) for item in data]
    if isinstance(data, tuple):
        return tuple(sanitize_data(item) for item in data)
    if isinstance(data, set):
        return {sanitize_data(item) for item in data}
    if hasattr(data, "model_dump"):
        return sanitize_data(data.model_dump())
    if hasattr(data, "__dict__"):
        return sanitize_data(data.__dict__)
    return sanitize_text(str(data))
