"""
Deterministic DummyAgent for Phase 2A test & verification.
"""

import time
from typing import Any, Dict, Optional

from agents.base import AgentResult, BaseAgent
from agents.registry import agent_registry
from core.constants import AgentTaskType, DummyAgentMode
from core.exceptions import NonRetryableAgentException, RetryableAgentException


class DummyAgent(BaseAgent):
    """
    Deterministic testing agent for Phase 2A infrastructure validation.
    """

    def __init__(self, name: str = "DummyAgent") -> None:
        super().__init__(name=name, default_task_type=AgentTaskType.DUMMY_TASK)

        self.invocation_counts: Dict[str, int] = {}

    def execute(self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """
        Execute deterministic testing logic based on payload configuration.

        Supported payload fields:
            mode (str): "SUCCESS", "TRANSIENT_FAILURE", "PERMANENT_FAILURE", "TIMEOUT"
            fail_count (int): Fail transiently N times before succeeding (default 0)
            sleep_seconds (float): Time to sleep (for timeout or delay testing)
            key (str): Identifier for tracking retry count in multi-step tests
        """
        mode = payload.get("mode", DummyAgentMode.SUCCESS.value)
        key = payload.get("key", "default_job")
        sleep_seconds = float(payload.get("sleep_seconds", 0.0))
        fail_count = int(payload.get("fail_count", 0))

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

        if mode == DummyAgentMode.PERMANENT_FAILURE.value:
            raise NonRetryableAgentException("Intentional deterministic permanent failure.")

        if mode == DummyAgentMode.TRANSIENT_FAILURE.value:
            current_attempts = self.invocation_counts.get(key, 0) + 1
            self.invocation_counts[key] = current_attempts

            if current_attempts <= fail_count:
                raise RetryableAgentException(
                    f"Intentional transient failure on attempt {current_attempts}/{fail_count}."
                )


        return AgentResult(
            success=True,
            task_type=self.default_task_type.value,
            agent_name=self.name,
            summary={
                "message": "Dummy agent execution completed successfully",
                "echo_payload": {k: v for k, v in payload.items() if k != "password"},
            },
            result_ref=f"dummy_ref_{key}",
            metadata={"attempts_recorded": self.invocation_counts.get(key, 1)},
        )



dummy_agent = DummyAgent()
agent_registry.register(dummy_agent, overwrite=True)
