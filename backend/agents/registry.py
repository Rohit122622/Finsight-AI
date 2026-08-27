"""
Central AgentRegistry for FinSentry AI.

Maintains all registered agents so Celery workers and API services can
dynamically lookup and execute agents without circular imports or hardcoded dispatchers.
"""

import logging
from typing import Dict, List

from agents.base import BaseAgent
from core.exceptions import AgentNotFoundException, DuplicateAgentException

logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Singleton registry for agent instances.
    """

    def __init__(self) -> None:
        self._agents: Dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent, overwrite: bool = False) -> None:
        """
        Register a new agent instance.

        Raises DuplicateAgentException if an agent with the same name exists and overwrite is False.
        """
        if not isinstance(agent, BaseAgent):
            raise TypeError(f"Expected BaseAgent instance, got {type(agent)}")

        if agent.name in self._agents and not overwrite:
            logger.warning("Attempted duplicate registration for agent '%s'", agent.name)
            raise DuplicateAgentException(agent.name)

        self._agents[agent.name] = agent
        logger.info("Registered agent '%s' (%s)", agent.name, agent.default_task_type)

    def get(self, agent_name: str) -> BaseAgent:
        """
        Retrieve a registered agent by name.

        Raises AgentNotFoundException if the agent is not registered.
        """
        if agent_name not in self._agents:
            logger.warning("Agent '%s' requested but not registered", agent_name)
            raise AgentNotFoundException(agent_name)
        return self._agents[agent_name]

    def list_agents(self) -> List[str]:
        """Return list of all registered agent names."""
        return sorted(list(self._agents.keys()))

    def unregister(self, agent_name: str) -> bool:
        """Remove an agent from the registry."""
        if agent_name in self._agents:
            del self._agents[agent_name]
            logger.info("Unregistered agent '%s'", agent_name)
            return True
        return False

    def clear(self) -> None:
        """Clear all registered agents (primarily for testing)."""
        self._agents.clear()



agent_registry = AgentRegistry()
