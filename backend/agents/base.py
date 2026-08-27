from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from core.constants import AgentTaskType


class AgentResult(BaseModel):
    """
    Standard output structure returned by all FinSentry AI agents.
    """

    success: bool = Field(..., description="Whether the agent execution completed successfully")
    task_type: str = Field(..., description="Task type executed")
    agent_name: str = Field(..., description="Name of the agent that produced this result")
    summary: Optional[Dict[str, Any]] = Field(
        default=None, description="Small, structured summary of the output"
    )
    result_ref: Optional[str] = Field(
        default=None, description="Reference pointer to large persisted artifacts/collections"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Execution metrics and metadata"
    )


class BaseAgent(ABC):
    """
    Abstract Base Class that all FinSentry AI agents must implement.
    """

    def __init__(self, name: str, default_task_type: AgentTaskType) -> None:
        self.name = name
        self.default_task_type = default_task_type

    @abstractmethod
    def execute(self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """
        Execute the agent logic.

        Must raise RetryableAgentException for transient failures,
        NonRetryableAgentException for permanent input/validation failures,
        or return AgentResult on success.
        """
        raise NotImplementedError("Subclasses must implement execute()")
