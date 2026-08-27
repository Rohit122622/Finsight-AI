"""
Core exception classes for FinSentry AI.
"""


class AppException(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str = "An internal application error occurred.") -> None:
        super().__init__(message)
        self.message = message


class BrokerUnavailableException(AppException):
    """Raised when the message broker (Redis/Celery) is unreachable."""

    def __init__(self, message: str = "Message broker is currently unavailable.") -> None:
        super().__init__(message)


class RetryableAgentException(AppException):
    """
    Transient exception during agent execution that is safe to retry.

    Examples: temporary network timeout, rate limit from external provider,
    transient database/redis glitch.
    """

    def __init__(self, message: str = "Transient agent execution failure; retryable.") -> None:
        super().__init__(message)


class NonRetryableAgentException(AppException):
    """
    Permanent failure during agent execution that must NOT be retried.

    Examples: malformed input data, schema validation error, invalid parameters.
    """

    def __init__(self, message: str = "Permanent agent execution failure; non-retryable.") -> None:
        super().__init__(message)


class AgentTimeoutException(AppException):
    """Raised when an agent execution exceeds its configured timeout window."""

    def __init__(self, message: str = "Agent execution timed out.") -> None:
        super().__init__(message)


class AgentNotFoundException(AppException):
    """Raised when an agent requested by name is not registered."""

    def __init__(self, agent_name: str) -> None:
        super().__init__(f"Agent '{agent_name}' is not registered in the AgentRegistry.")
        self.agent_name = agent_name


class DuplicateAgentException(AppException):
    """Raised when attempting to register an agent name that already exists."""

    def __init__(self, agent_name: str) -> None:
        super().__init__(f"Agent '{agent_name}' is already registered in the AgentRegistry.")
        self.agent_name = agent_name


class JobNotFoundException(AppException):
    """Raised when a job is not found by its ID."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job with ID '{job_id}' was not found.")
        self.job_id = job_id


class UnauthorizedJobAccessException(AppException):
    """Raised when a user attempts to access a job they do not own."""

    def __init__(self, message: str = "You do not have permission to access this job.") -> None:
        super().__init__(message)


class DocumentNotFoundException(AppException):
    """Raised when a document is not found by its ID."""

    def __init__(self, document_id: str) -> None:
        super().__init__(f"Document with ID '{document_id}' was not found.")
        self.document_id = document_id


class InvalidDocumentException(AppException):
    """Raised when an uploaded document fails validation or parsing."""

    def __init__(self, message: str = "Invalid or unsupported document format.") -> None:
        super().__init__(message)


class UnauthorizedDocumentAccessException(AppException):
    """Raised when a user attempts to access a document they do not own."""

    def __init__(self, message: str = "You do not have permission to access this document.") -> None:
        super().__init__(message)


class DuplicateDocumentException(AppException):
    """Raised when an identical document hash is uploaded for the same user/session."""

    def __init__(self, message: str = "Duplicate document detected. This exact file has already been uploaded.") -> None:
        super().__init__(message)


class MalwareDetectedException(AppException):
    """Raised when malware or virus signature is detected in an uploaded file."""

    def __init__(self, message: str = "Malware detected in uploaded file.") -> None:
        super().__init__(message)


class ScannerUnavailableException(AppException):
    """Raised when the antivirus scanner is unreachable and fail-closed policy is active."""

    def __init__(self, message: str = "Antivirus scanning service is currently unavailable.") -> None:
        super().__init__(message)


class CorruptedDocumentException(AppException):
    """Raised when an uploaded document has corrupted structure or cannot be decoded."""

    def __init__(self, message: str = "Uploaded document is corrupted or malformed.") -> None:
        super().__init__(message)


class PageLimitExceededException(AppException):
    """Raised when an uploaded document exceeds the allowed page count limit."""

    def __init__(self, message: str = "Document exceeds maximum allowed page count.") -> None:
        super().__init__(message)


class UploadRateLimitException(AppException):
    """Raised when a user exceeds the allowed upload frequency."""

    def __init__(self, message: str = "Upload rate limit exceeded. Please wait before uploading more documents.") -> None:
        super().__init__(message)


class StorageServiceException(AppException):
    """Raised when private storage operations (e.g. Cloudflare R2) fail."""

    def __init__(self, message: str = "Storage service operation failed.") -> None:
        super().__init__(message)
