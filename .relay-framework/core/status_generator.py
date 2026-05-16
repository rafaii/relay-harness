"""
Status Dashboard Generator
===========================

Generates task_status.md dashboard from database.
"""

from datetime import datetime
from pathlib import Path
from typing import List

from .database import TaskDatabase, Task, TaskLog
from .agent_pool import AgentPool
from .task_scheduler import TaskScheduler


def generate_status_dashboard(project_dir: Path, pool: AgentPool = None, scheduler: TaskScheduler = None):
    """
    Generate task_status.md from database.

    Args:
        project_dir: Project directory
        pool: Optional agent pool (for active agents info)
        scheduler: Optional scheduler (for queue info)
    """
    db = TaskDatabase(project_dir)
    docs_dir = project_dir / "docs"
    docs_dir.mkdir(exist_ok=True)

    status_file = docs_dir / "task_status.md"

    # Get data
    stats = db.get_statistics()
    tasks_by_phase = db.get_tasks_grouped_by_phase()
    recent_activity = db.get_recent_activity(limit=10)

    # Build markdown
    content = _build_markdown(stats, tasks_by_phase, recent_activity, pool, scheduler)

    # Write file
    status_file.write_text(content)


def _build_markdown(stats: dict, tasks_by_phase: dict, recent_activity: List[TaskLog],
                     pool: AgentPool = None, scheduler: TaskScheduler = None) -> str:
    """Build markdown content."""
    lines = []

    # Header
    lines.append("# Project Status Dashboard\n")
    lines.append(f"**Last Updated:** {datetime.now().strftime('%b %d, %Y at %I:%M%p')}\n")

    completion_pct = (stats['completed'] / stats['total'] * 100) if stats['total'] > 0 else 0
    lines.append(f"**Overall Progress:** {stats['completed']}/{stats['total']} tasks ({completion_pct:.1f}%)\n")
    lines.append("\n---\n")

    # Agent Pool Status
    if pool:
        lines.append(_format_agent_pool_section(pool))

    # Queue Info
    if scheduler:
        lines.append(_format_queue_section(scheduler))

    # Phase Breakdown
    for phase, tasks in tasks_by_phase.items():
        lines.append(_format_phase_section(phase, tasks))

    # Recent Activity
    if recent_activity:
        lines.append(_format_recent_activity(recent_activity))

    # Statistics
    lines.append(_format_statistics(stats))

    return "\n".join(lines)


def _format_agent_pool_section(pool: AgentPool) -> str:
    """Format agent pool status section."""
    lines = []
    lines.append("## Agent Pool Status\n")

    capacity = pool.get_capacity_info()
    lines.append(f"**Active Agents:** {capacity['used']}/{capacity['total']} slots used\n")

    active_agents = pool.get_active_agents()
    if active_agents:
        lines.append("\n| Agent | Type | Current Task | Status |")
        lines.append("|-------|------|--------------|--------|")
        for agent in active_agents:
            task_id = agent.current_task_id or "-"
            status = "Working" if agent.current_task_id else "Idle"
            lines.append(f"| **{agent.agent_name}** | {agent.agent_type.title()} | {task_id} | {status} |")
    else:
        lines.append("\n*No active agents*")

    lines.append("\n---\n")
    return "\n".join(lines)


def _format_queue_section(scheduler: TaskScheduler) -> str:
    """Format queue section."""
    lines = []
    queued = scheduler.get_queued_tasks()

    if queued:
        lines.append(f"## Queued Tasks: {len(queued)} waiting for agents\n")
        lines.append("\n### Ready Queue")
        for i, task in enumerate(queued[:5], 1):  # Show top 5
            agent_type = scheduler.get_required_agent_type(task.status)
            lines.append(f"{i}. **{task.id}** - {task.title} (needs {agent_type})")

        if len(queued) > 5:
            lines.append(f"\n... and {len(queued) - 5} more")

        lines.append("\n---\n")

    return "\n".join(lines)


def _format_phase_section(phase: str, tasks: List[Task]) -> str:
    """Format phase section."""
    lines = []

    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == 'done')
    in_progress = sum(1 for t in tasks if t.status in ['in_development', 'in_qa', 'in_security'])
    todo = sum(1 for t in tasks if t.status == 'todo')

    progress_pct = (completed / total * 100) if total > 0 else 0

    lines.append(f"## Phase: {phase} ({completed}/{total} - {progress_pct:.0f}%)\n")

    # Completed
    completed_tasks = [t for t in tasks if t.status == 'done']
    if completed_tasks:
        lines.append(f"### ✅ Completed ({len(completed_tasks)})")
        for task in completed_tasks[:5]:  # Show first 5
            lines.append(f"- **{task.id}** - {task.title}")
        if len(completed_tasks) > 5:
            lines.append(f"- ... and {len(completed_tasks) - 5} more\n")
        else:
            lines.append("")

    # In Progress
    in_progress_tasks = [t for t in tasks if t.status in ['in_development', 'in_qa', 'in_security']]
    if in_progress_tasks:
        lines.append(f"### 🔄 In Progress ({len(in_progress_tasks)})")
        for task in in_progress_tasks:
            status_display = task.status.replace('_', ' ').title()
            assignee_info = f" (by {task.assignee})" if task.assignee else ""
            lines.append(f"- **{task.id}** - {task.title} - {status_display}{assignee_info}")
        lines.append("")

    # To Do
    todo_tasks = [t for t in tasks if t.status == 'todo']
    if todo_tasks:
        lines.append(f"### 📋 To Do ({len(todo_tasks)})")
        for task in todo_tasks[:3]:  # Show first 3
            lines.append(f"- **{task.id}** - {task.title}")
        if len(todo_tasks) > 3:
            lines.append(f"- ... and {len(todo_tasks) - 3} more")
        lines.append("")

    lines.append("---\n")
    return "\n".join(lines)


def _format_recent_activity(logs: List[TaskLog]) -> str:
    """Format recent activity section."""
    lines = []
    lines.append("## Recent Activity\n")

    for i, log in enumerate(logs, 1):
        time = log.created_at.strftime('%I:%M%p') if log.created_at else "Unknown"
        lines.append(f"{i}. **{time}** - {log.agent_name} ({log.agent_type}): {log.action} on {log.task_id}")

    lines.append("\n---\n")
    return "\n".join(lines)


def _format_statistics(stats: dict) -> str:
    """Format statistics section."""
    lines = []
    lines.append("## Statistics\n")
    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Total Tasks | {stats['total']} |")
    lines.append(f"| Completed | {stats['completed']} |")
    lines.append(f"| To Do | {stats.get('todo', 0)} |")
    lines.append(f"| In Development | {stats.get('in_development', 0)} |")
    lines.append(f"| In QA | {stats.get('in_qa', 0)} |")
    lines.append(f"| In Security | {stats.get('in_security', 0)} |")

    return "\n".join(lines)
