import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.config import get_settings
from utils.sanitization import sanitize_data

logger = logging.getLogger(__name__)

                                    
try:
    from langsmith import Client as LangSmithClient
    _LANGSMITH_AVAILABLE = True
except ImportError:
    LangSmithClient = None                
    _LANGSMITH_AVAILABLE = False


class LangSmithService:
    """
    Manages LangSmith trace collection and run lifecycle for FinSentry AI.
    Guarantees that telemetry failures never interrupt the primary research flow.
    """

    def __init__(self) -> None:
        self._client: Optional[Any] = None
        self._initialized: bool = False
        self._is_enabled: bool = False

    def _ensure_client(self) -> None:
        """Lazily initialize the LangSmith client if configured."""
        if self._initialized:
            return

        self._initialized = True
        settings = get_settings()

        if not _LANGSMITH_AVAILABLE:
            logger.info("LangSmith library not installed. Operating in no-op mode.")
            self._is_enabled = False
            return

        if not settings.LANGSMITH_ENABLED or not settings.LANGSMITH_API_KEY:
            logger.info("LangSmith is disabled or API key is not configured.")
            self._is_enabled = False
            return

        try:
            self._client = LangSmithClient(
                api_key=settings.LANGSMITH_API_KEY,
                api_url=settings.LANGSMITH_ENDPOINT or "https://api.smith.langchain.com",
            )
            self._is_enabled = True
            logger.info(
                "LangSmith client initialized successfully for project '%s'.",
                settings.LANGSMITH_PROJECT,
            )
        except Exception as exc:
            logger.warning("Failed to initialize LangSmith client: %s. Falling back to no-op.", exc)
            self._client = None
            self._is_enabled = False

    @property
    def is_enabled(self) -> bool:
        """Check if LangSmith tracing is currently active."""
        self._ensure_client()
        return self._is_enabled and self._client is not None

    def create_root_run(
        self,
        trace_id: str,
        session_id: str,
        conversation_id: str,
        user_id: str,
        query: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Create a root run representing the full Research Agent execution.
        Returns the root run_id string, or None if LangSmith is disabled/unavailable.
        """
        if not self.is_enabled:
            return None

        settings = get_settings()
        run_id = str(uuid.uuid4())
        sanitized_query = sanitize_data(query)
        sanitized_meta = sanitize_data(metadata or {})
        sanitized_meta.update({
            "trace_id": trace_id,
            "session_id": session_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "agent_name": "ResearchAgent",
        })

        try:
            self._client.create_run(
                id=run_id,
                name="ResearchAgent.chat",
                run_type="chain",
                inputs={"query": sanitized_query},
                project_name=settings.LANGSMITH_PROJECT,
                extra={"metadata": sanitized_meta},
                start_time=datetime.now(timezone.utc),
            )
            return run_id
        except Exception as exc:
            logger.debug("Non-fatal LangSmith create_root_run error: %s", exc)
            return None

    def create_child_run(
        self,
        parent_run_id: Optional[str],
        name: str,
        run_type: str = "chain",
        inputs: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Create a child run under the specified parent run.
        """
        if not self.is_enabled or not parent_run_id:
            return None

        settings = get_settings()
        run_id = str(uuid.uuid4())
        sanitized_inputs = sanitize_data(inputs or {})
        sanitized_meta = sanitize_data(metadata or {})

        try:
            self._client.create_run(
                id=run_id,
                name=name,
                run_type=run_type,
                inputs=sanitized_inputs,
                parent_run_id=parent_run_id,
                project_name=settings.LANGSMITH_PROJECT,
                extra={"metadata": sanitized_meta},
                start_time=datetime.now(timezone.utc),
            )
            return run_id
        except Exception as exc:
            logger.debug("Non-fatal LangSmith create_child_run error: %s", exc)
            return None

    def end_run(
        self,
        run_id: Optional[str],
        outputs: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        end_time: Optional[datetime] = None,
    ) -> None:
        """
        End an active LangSmith run with sanitized outputs or error description.
        """
        if not self.is_enabled or not run_id:
            return

        sanitized_outputs = sanitize_data(outputs) if outputs else None
        sanitized_error = sanitize_data(error) if error else None

        try:
            self._client.update_run(
                run_id=run_id,
                outputs=sanitized_outputs,
                error=sanitized_error,
                end_time=end_time or datetime.now(timezone.utc),
            )
        except Exception as exc:
            logger.debug("Non-fatal LangSmith end_run error: %s", exc)

    def get_trace_url(self, run_id: Optional[str]) -> Optional[str]:
        """
        Generate LangSmith web trace URL for the given run if available.
        """
        if not self.is_enabled or not run_id:
            return None

        settings = get_settings()
        try:
            base_endpoint = settings.LANGSMITH_ENDPOINT.rstrip("/")
                                         
            if "api.smith.langchain.com" in base_endpoint:
                return f"https://smith.langchain.com/o/default/projects/p/{settings.LANGSMITH_PROJECT}/r/{run_id}"
            return f"{base_endpoint}/projects/{settings.LANGSMITH_PROJECT}/runs/{run_id}"
        except Exception:
            return None


langsmith_service = LangSmithService()
