"""Project Status Routes"""

from fastapi import APIRouter, HTTPException
from core.registry import get_project_path
from core.database import TaskDatabase

router = APIRouter()


@router.get("/projects/{name}/status")
async def get_status(name: str):
    """Get project status and statistics."""
    project_path = get_project_path(name)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    db = TaskDatabase(project_path)
    stats = db.get_statistics()
    tasks_by_phase = db.get_tasks_grouped_by_phase()

    # Convert to simple structure
    phases = {}
    for phase, tasks in tasks_by_phase.items():
        phases[phase] = {
            "total": len(tasks),
            "completed": sum(1 for t in tasks if t.status == 'done'),
            "in_progress": sum(1 for t in tasks if t.status in ['in_development', 'in_qa', 'in_security'])
        }

    return {
        "statistics": stats,
        "phases": phases
    }
