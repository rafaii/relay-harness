"""Task Management Routes"""

from fastapi import APIRouter, HTTPException
from pathlib import Path
from core.registry import get_project_path
from core.database import TaskDatabase

router = APIRouter()


@router.get("/projects/{name}/tasks")
async def list_tasks(name: str):
    """List all tasks for a project."""
    project_path = get_project_path(name)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    db = TaskDatabase(project_path)
    tasks = db.get_all_tasks()
    return [task.to_dict() for task in tasks]


@router.get("/projects/{name}/tasks/{task_id}")
async def get_task(name: str, task_id: str):
    """Get specific task details."""
    project_path = get_project_path(name)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    db = TaskDatabase(project_path)
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return task.to_dict()
