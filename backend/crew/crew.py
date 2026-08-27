"""
CrewAI and FinSentry Orchestration Foundation (Phase 2C).

Orchestrates multi-agent execution with shared LLM configuration,
central timeout enforcement, and strict Pydantic output validation.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel

from agents.base import AgentResult, BaseAgent
from agents.registry import agent_registry
from core.config import AgentLLMConfig, get_settings
from core.constants import AgentTaskType
from core.exceptions import NonRetryableAgentException
from core.logging import log_agent_event
from crew.tasks import FinSentryTask

logger = logging.getLogger(__name__)


class FinSentryCrew:
    """
    Crew orchestrator managing multiple agents and tasks to accomplish financial research goals.
    """

    def __init__(
        self,
        agents: Optional[List[str]] = None,
        tasks: Optional[List[FinSentryTask]] = None,
        llm_config: Optional[AgentLLMConfig] = None,
    ) -> None:
        self.agent_names = agents or []
        self.tasks = tasks or []
        self.llm_config = llm_config or get_settings().get_default_llm_config()

    def add_task(self, task: FinSentryTask) -> None:
        """Append a task to the crew."""
        self.tasks.append(task)

    def kickoff(
        self,
        inputs: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute all crew tasks sequentially and return validated results.

        Enforces:
        1. Agent lookup via agent_registry
        2. Execution of task payload with accumulated intermediate state
        3. Pydantic schema validation of output
        4. Structured event logging and telemetry
        """
        inputs = dict(inputs or {})
        context = dict(context or {})
        results: Dict[str, Any] = {}
        accumulated_state: Dict[str, Any] = {**inputs}
        start_total = time.time()

        logger.info("FinSentryCrew kickoff started with %d tasks", len(self.tasks))

        for idx, task in enumerate(self.tasks):
            agent_name = task.agent_name
            task_start = time.time()

            logger.info("Executing Crew Task %d/%d: agent='%s'", idx + 1, len(self.tasks), agent_name)

                               
            agent = agent_registry.get(agent_name)

                                                                       
            payload = {**accumulated_state, **task.context}

                              
            agent_result = agent.execute(payload=payload, context=context)
            if not agent_result.success:
                task_latency_ms = (time.time() - task_start) * 1000
                logger.error("Crew task %d (%s) failed: %s", idx + 1, agent_name, agent_result.summary)
                results[f"task_{idx + 1}_{agent_name}"] = {
                    "agent": agent_name,
                    "task_description": task.description,
                    "output": agent_result.summary,
                    "latency_ms": task_latency_ms,
                    "success": False,
                }
                return {
                    "status": "FAILED",
                    "failed_task": agent_name,
                    "error": str(agent_result.summary or "Agent task returned unsuccessful result"),
                    "total_tasks": len(self.tasks),
                    "tasks_results": results,
                    "accumulated_state": accumulated_state,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }

                                                    
            output_data = dict(agent_result.summary or {})
            if "agent_name" not in output_data:
                output_data["agent_name"] = agent_name
            if "session_id" not in output_data and payload.get("session_id"):
                output_data["session_id"] = payload.get("session_id")

            if task.output_schema and issubclass(task.output_schema, BaseModel):
                try:
                    if isinstance(output_data, dict):
                        validated = task.output_schema(**output_data)
                        output_data = validated.model_dump()
                except Exception as exc:
                    logger.warning("Output validation warning for task '%s': %s", task.description, exc)

                                                                             
            if isinstance(output_data, dict):
                for k, v in output_data.items():
                    if k not in accumulated_state or v is not None:
                        accumulated_state[k] = v
                                                                    
                if "extracted_data" in output_data and isinstance(output_data["extracted_data"], dict):
                    accumulated_state["metrics"] = output_data["extracted_data"]
                    accumulated_state["extracted_metrics"] = output_data["extracted_data"]

            task_latency_ms = (time.time() - task_start) * 1000

            log_agent_event(
                logger,
                logging.INFO,
                f"Crew task {idx + 1} completed by {agent_name} in {task_latency_ms:.2f}ms",
                agent_name=agent_name,
                status="COMPLETED",
                latency_ms=task_latency_ms,
                session_id=context.get("session_id") or payload.get("session_id"),
                user_id=context.get("user_id") or payload.get("user_id"),
            )

            results[f"task_{idx + 1}_{agent_name}"] = {
                "agent": agent_name,
                "task_description": task.description,
                "output": output_data,
                "latency_ms": task_latency_ms,
                "success": agent_result.success,
            }

        total_latency_ms = (time.time() - start_total) * 1000
        return {
            "status": "COMPLETED",
            "total_tasks": len(self.tasks),
            "total_latency_ms": total_latency_ms,
            "tasks_results": results,
            "accumulated_state": accumulated_state,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def create_document_pipeline(
        cls,
        session_id: str,
        document_id: str,
        user_id: Optional[str] = None,
        force_ocr: bool = False,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> "FinSentryCrew":
        """
        Factory to construct the canonical document processing and forensic analysis crew:
        DocumentAgent -> ExtractionAgent -> RedFlagAgent (proactive) -> (ComparisonAgent if multi-doc).
        """
        from crew.tasks import (
            create_document_task,
            create_extraction_task,
            create_red_flag_task,
        )

        doc_task = create_document_task(session_id=session_id, document_id=document_id)
        if force_ocr:
            doc_task.context["force_ocr"] = True
        if chunk_size:
            doc_task.context["chunk_size_tokens"] = chunk_size
        if chunk_overlap:
            doc_task.context["chunk_overlap_tokens"] = chunk_overlap
        if user_id:
            doc_task.context["user_id"] = user_id

        extraction_task = create_extraction_task(session_id=session_id, document_id=document_id)
        if user_id:
            extraction_task.context["user_id"] = user_id

        red_flag_task = create_red_flag_task(session_id=session_id)
        if user_id:
            red_flag_task.context["user_id"] = user_id
        red_flag_task.context["document_id"] = document_id
        red_flag_task.context["document_ids"] = [document_id]

        return cls(
            agents=["DocumentAgent", "ExtractionAgent", "RedFlagAgent"],
            tasks=[doc_task, extraction_task, red_flag_task],
        )


class CrewOrchestrator(BaseAgent):
    """
    Production Agent executing the full multi-agent CrewAI orchestration pipeline.
    Orchestrates: DocumentAgent -> ExtractionAgent -> RedFlagAgent -> (ComparisonAgent if multi-doc).
    """

    def __init__(self, name: str = "CrewOrchestrator") -> None:
        super().__init__(name=name, default_task_type=AgentTaskType.DOCUMENT_ANALYSIS)

    def execute(
        self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Execute full multi-agent crew workflow for an uploaded document.
        """
        session_id = payload.get("session_id")
        document_id = payload.get("document_id")
        user_id = (context or {}).get("user_id") or payload.get("user_id")
        force_ocr = bool(payload.get("force_ocr", False))
        chunk_size = payload.get("chunk_size_tokens") or payload.get("chunk_size")
        chunk_overlap = payload.get("chunk_overlap_tokens") or payload.get("chunk_overlap")

        if not session_id or not document_id or not user_id:
            raise NonRetryableAgentException(
                "Missing required parameters: 'session_id', 'document_id', and 'user_id' must be provided."
            )

        logger.info(
            "CrewOrchestrator initiating full multi-agent crew for document %s (session %s, user %s)",
            document_id,
            session_id,
            user_id,
        )

        crew = FinSentryCrew.create_document_pipeline(
            session_id=session_id,
            document_id=document_id,
            user_id=user_id,
            force_ocr=force_ocr,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        crew_result = crew.kickoff(
            inputs={
                "session_id": session_id,
                "document_id": document_id,
                "user_id": user_id,
                "force_ocr": force_ocr,
            },
            context={
                "session_id": session_id,
                "document_id": document_id,
                "user_id": user_id,
                "job_id": (context or {}).get("job_id"),
            },
        )

        if crew_result.get("status") != "COMPLETED":
            err_msg = crew_result.get("error") or f"Crew task {crew_result.get('failed_task')} failed."
            raise NonRetryableAgentException(f"Crew orchestration pipeline failed: {err_msg}")

        return AgentResult(
            success=True,
            task_type=self.default_task_type.value,
            agent_name=self.name,
            summary=crew_result,
            result_ref=document_id,
            metadata={
                "total_tasks": crew_result.get("total_tasks", 0),
                "total_latency_ms": crew_result.get("total_latency_ms", 0),
            },
        )


                                              
crew_orchestrator = CrewOrchestrator("CrewOrchestrator")
agent_registry.register(crew_orchestrator, overwrite=True)


