"""Agent Status Routes"""

from fastapi import APIRouter, HTTPException
from core.registry import get_project_path
from core.database import TaskDatabase

router = APIRouter()


@router.get("/projects/{name}/agents")
async def list_agents(name: str):
    """List active agents for a project."""
    project_path = get_project_path(name)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    db = TaskDatabase(project_path)
    agents = db.get_active_agents()
    return [agent.to_dict() for agent in agents]
