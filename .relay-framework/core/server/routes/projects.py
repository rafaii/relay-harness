"""Project Management Routes"""

from fastapi import APIRouter, HTTPException
from pathlib import Path
from core.registry import list_registered_projects, get_project_path

router = APIRouter()


@router.get("/projects")
async def list_projects():
    """List all registered projects."""
    return list_registered_projects()


@router.get("/projects/{name}")
async def get_project(name: str):
    """Get project details."""
    project_path = get_project_path(name)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    return {
        "name": name,
        "path": str(project_path),
        "exists": project_path.exists()
    }
