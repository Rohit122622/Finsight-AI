"""
FastAPI router for inspecting registered FinSentry AI agents (Phase 2B).
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from agents.registry import agent_registry
from core.exceptions import AgentNotFoundException
from middleware.auth_middleware import get_current_user
from models.user import UserModel

logger = logging.getLogger(__name__)

router = APIRouter()


class AgentInfoResponse(BaseModel):
    """Metadata description of a registered agent."""

    name: str
    task_type: str
    description: str
    is_active: bool = True


@router.get(
    "",
    response_model=List[AgentInfoResponse],
    summary="List all registered agents",
)
async def list_registered_agents(
    current_user: UserModel = Depends(get_current_user),
) -> Any:
    """
    Query the active AgentRegistry to list all discoverable agents and capabilities.
    """
    agents_list = []
    for name in agent_registry.list_agents():
        agent = agent_registry.get(name)
        agents_list.append(
            AgentInfoResponse(
                name=agent.name,
                task_type=agent.default_task_type.value if hasattr(agent.default_task_type, "value") else str(agent.default_task_type),
                description=agent.__doc__.strip() if agent.__doc__ else "FinSentry AI Agent",
                is_active=True,
            )
        )
    return agents_list


@router.get(
    "/status",
    summary="Get overall agent system health and registered agents status",
)
async def get_agents_status(
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Returns registered agents count, list, and system readiness.
    """
    registered = agent_registry.list_agents()
    return {
        "status": "healthy",
        "registered_agents_count": len(registered),
        "registered_agents": registered,
        "required_agents": [
            "DocumentAgent",
            "ExtractionAgent",
            "RedFlagAgent",
            "ComparisonAgent",
            "ResearchAgent",
            "ReportAgent",
        ],
        "all_required_present": all(
            req in registered for req in [
                "DocumentAgent",
                "ExtractionAgent",
                "RedFlagAgent",
                "ComparisonAgent",
                "ResearchAgent",
                "ReportAgent",
            ]
        ),
    }


@router.get(
    "/{agent_name}",
    response_model=AgentInfoResponse,
    summary="Get details of a specific registered agent",
)
async def get_agent_details(
    agent_name: str,
    current_user: UserModel = Depends(get_current_user),
) -> Any:
    """
    Retrieve metadata for a single registered agent.
    """
    try:
        agent = agent_registry.get(agent_name)
        return AgentInfoResponse(
            name=agent.name,
            task_type=agent.default_task_type.value if hasattr(agent.default_task_type, "value") else str(agent.default_task_type),
            description=agent.__doc__.strip() if agent.__doc__ else "FinSentry AI Agent",
            is_active=True,
        )
    except AgentNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_name}' is not registered.",
        )
