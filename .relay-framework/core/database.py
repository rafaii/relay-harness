"""
Task Database
=============

SQLite database for task management with SQLAlchemy ORM.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Any

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    ForeignKey,
    create_engine,
    Index,
    text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker, relationship
from sqlalchemy.pool import StaticPool

Base = declarative_base()


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


class Task(Base):
    """Task model for multi-agent execution with 9-state workflow."""

    __tablename__ = "tasks"

    # Primary key: string ID like "ARC-001", "ARC-002"
    id = Column(String(50), primary_key=True)

    # Task metadata
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # 11-state workflow status (SINGLE field for entire workflow)
    # States: todo, in_development, qa_fixing, security_fixing, ready_for_qa,
    #         in_qa, qa_failed, ready_for_security, in_security, security_failed, done
    status = Column(String(50), default="todo", nullable=False, index=True)

    # Phase grouping (foundation, features, polish, etc.)
    phase = Column(String(100), nullable=True, index=True)

    # Current assignee (agent_id)
    assignee = Column(String(100), nullable=True)

    # Dependencies (JSON array of task IDs)
    dependencies = Column(Text, nullable=True)  # Stored as JSON string

    # Priority (higher = more important)
    priority = Column(Integer, default=0, nullable=False, index=True)

    # Complexity estimate (1-5)
    complexity = Column(Integer, default=3, nullable=True)

    # Role assignment (frontend_developer, backend_developer, qa, security)
    role = Column(String(50), nullable=True)

    # Agent type for reassignment after QA/Security failures ('frontend' or 'backend')
    # This tracks the original developer type so failed tasks can be routed back correctly
    agent_type = Column(String(20), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)

    # Relationships
    logs = relationship("TaskLog", back_populates="task", cascade="all, delete-orphan")

    def get_dependencies(self) -> List[str]:
        """Get task dependencies as list."""
        if not self.dependencies:
            return []
        try:
            return json.loads(self.dependencies)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_dependencies(self, deps: List[str]):
        """Set task dependencies from list."""
        self.dependencies = json.dumps(deps) if deps else None

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "phase": self.phase,
            "assignee": self.assignee,
            "dependencies": self.get_dependencies(),
            "priority": self.priority,
            "complexity": self.complexity,
            "role": self.role,
            "agent_type": self.agent_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TaskLog(Base):
    """Task log for tracking agent actions."""

    __tablename__ = "task_logs"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Task reference
    task_id = Column(String(50), ForeignKey("tasks.id"), nullable=False, index=True)

    # Agent info (normalized - join with agents table for name/type)
    agent_id = Column(String(100), ForeignKey("agents.agent_id"), nullable=False)

    # Action details
    action = Column(String(50), nullable=False)  # started, completed, failed, etc.
    status = Column(String(50), nullable=True)  # passed, failed (for QA/Security)
    notes = Column(Text, nullable=True)  # Additional details

    # Timestamp
    created_at = Column(DateTime, default=_utc_now, nullable=False, index=True)

    # Relationships
    task = relationship("Task", back_populates="logs")

    def to_dict(self) -> Dict[str, Any]:
        """Convert log to dictionary.

        Note: agent_name and agent_type can be retrieved by joining with agents table:
        SELECT tl.*, a.agent_name, a.agent_type
        FROM task_logs tl
        JOIN agents a ON tl.agent_id = a.agent_id
        """
        return {
            "id": self.id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "action": self.action,
            "status": self.status,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Agent(Base):
    """Agent tracking table.

    Note: Current task assignment is tracked via tasks.assignee field, not here.
    This prevents data silos and ensures tasks table is the single source of truth.
    """

    __tablename__ = "agents"

    # Primary key: agent_id like "developer_1"
    agent_id = Column(String(100), primary_key=True)

    # Agent info
    agent_name = Column(String(100), nullable=False)  # "Maya"
    agent_type = Column(String(50), nullable=False)  # developer, qa, security

    # REMOVED: current_task_id - Use tasks.assignee instead to prevent data silos
    # To find an agent's current task: SELECT * FROM tasks WHERE assignee = 'agent_id'
    # To check if agent is available: SELECT COUNT(*) FROM tasks WHERE assignee = 'agent_id' == 0

    # Stats
    tasks_completed = Column(Integer, default=0, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    last_active = Column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert agent to dictionary."""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "tasks_completed": self.tasks_completed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_active": self.last_active.isoformat() if self.last_active else None,
        }


class ProjectMetadata(Base):
    """Project metadata key-value store."""

    __tablename__ = "project_metadata"

    # Key-value pairs
    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)  # JSON-encoded value

    def get_value(self) -> Any:
        """Get decoded value."""
        if not self.value:
            return None
        try:
            return json.loads(self.value)
        except (json.JSONDecodeError, TypeError):
            return self.value

    def set_value(self, val: Any):
        """Set encoded value."""
        self.value = json.dumps(val) if val is not None else None


# Create indexes for performance
Index('idx_task_status_phase', Task.status, Task.phase)
Index('idx_task_assignee', Task.assignee)
Index('idx_tasklog_task_created', TaskLog.task_id, TaskLog.created_at)


class TaskDatabase:
    """Task database operations."""

    def __init__(self, project_dir: Path):
        """
        Initialize task database.

        Args:
            project_dir: Project directory containing .relay folder
        """
        self.project_dir = project_dir
        relay_dir = project_dir / ".relay"
        relay_dir.mkdir(parents=True, exist_ok=True)

        db_path = relay_dir / "tasks.db"

        # Configure SQLite for better concurrency
        # - check_same_thread=False: Allow multi-threaded access
        # - timeout=30: Wait up to 30 seconds for locks
        # - StaticPool: Use static pool for SQLite (better for multi-process)
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={
                "check_same_thread": False,
                "timeout": 30
            },
            poolclass=StaticPool
        )

        # Create all tables
        Base.metadata.create_all(self.engine)

        # Enable WAL mode and busy timeout for better concurrency
        # WAL mode allows multiple readers + 1 writer concurrently
        # busy_timeout retries operations for 5 seconds instead of failing immediately
        with self.engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA busy_timeout=5000"))
            conn.commit()

        self.Session = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        """Get new database session."""
        return self.Session()

    # Task operations
    def create_task(self, task_data: Dict[str, Any]) -> Task:
        """Create a new task."""
        session = self.get_session()
        try:
            task = Task(**task_data)
            if 'dependencies' in task_data and isinstance(task_data['dependencies'], list):
                task.set_dependencies(task_data['dependencies'])

            session.add(task)
            session.commit()
            session.refresh(task)
            return task
        finally:
            session.close()

    def update_task(self, task_id: str, updates: Dict[str, Any]) -> Optional[Task]:
        """Update a task."""
        session = self.get_session()
        try:
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                return None

            for key, value in updates.items():
                if key == 'dependencies' and isinstance(value, list):
                    task.set_dependencies(value)
                elif hasattr(task, key):
                    setattr(task, key, value)

            task.updated_at = _utc_now()
            session.commit()
            session.refresh(task)
            return task
        finally:
            session.close()

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a single task."""
        session = self.get_session()
        try:
            return session.query(Task).filter_by(id=task_id).first()
        finally:
            session.close()

    def get_all_tasks(self) -> List[Task]:
        """Get all tasks."""
        session = self.get_session()
        try:
            return session.query(Task).order_by(Task.priority.desc(), Task.created_at).all()
        finally:
            session.close()

    def get_tasks_by_status(self, status: str) -> List[Task]:
        """Get tasks by status."""
        session = self.get_session()
        try:
            return session.query(Task).filter_by(status=status).order_by(Task.priority.desc()).all()
        finally:
            session.close()

    def get_tasks_by_phase(self, phase: str) -> List[Task]:
        """Get tasks by phase."""
        session = self.get_session()
        try:
            return session.query(Task).filter_by(phase=phase).order_by(Task.priority.desc()).all()
        finally:
            session.close()

    def get_tasks_grouped_by_phase(self) -> Dict[str, List[Task]]:
        """Get all tasks grouped by phase."""
        tasks = self.get_all_tasks()
        grouped = {}
        for task in tasks:
            phase = task.phase or "Other"
            if phase not in grouped:
                grouped[phase] = []
            grouped[phase].append(task)
        return grouped

    def get_next_ready_task(self) -> Optional[Task]:
        """Get next ready task (dependencies resolved, not assigned).

        Ready tasks are those with status: todo, qa_failed, or security_failed.
        """
        session = self.get_session()
        try:
            # Get all tasks that need development work (todo, qa_failed, security_failed)
            tasks = session.query(Task).filter(
                Task.status.in_(["todo", "qa_failed", "security_failed"]),
                Task.assignee.is_(None)
            ).order_by(Task.priority.desc()).all()

            # Check dependencies
            for task in tasks:
                deps = task.get_dependencies()
                if not deps:
                    return task

                # Check if all dependencies are done
                deps_done = True
                for dep_id in deps:
                    dep_task = session.query(Task).filter_by(id=dep_id).first()
                    if not dep_task or dep_task.status != "done":
                        deps_done = False
                        break

                if deps_done:
                    return task

            return None
        finally:
            session.close()

    # Task log operations
    def log_action(
        self,
        task_id: str,
        agent_id: str,
        action: str,
        status: Optional[str] = None,
        notes: Optional[str] = None
    ) -> TaskLog:
        """
        Log an agent action.

        Note: agent_name and agent_type are retrieved via join with agents table.
        """
        session = self.get_session()
        try:
            log = TaskLog(
                task_id=task_id,
                agent_id=agent_id,
                action=action,
                status=status,
                notes=notes
            )
            session.add(log)
            session.commit()
            session.refresh(log)
            return log
        finally:
            session.close()

    def get_task_logs(self, task_id: str) -> List[TaskLog]:
        """Get logs for a task."""
        session = self.get_session()
        try:
            return session.query(TaskLog).filter_by(task_id=task_id).order_by(TaskLog.created_at).all()
        finally:
            session.close()

    def get_recent_activity(self, limit: int = 10) -> List[TaskLog]:
        """Get recent activity logs."""
        session = self.get_session()
        try:
            return session.query(TaskLog).order_by(TaskLog.created_at.desc()).limit(limit).all()
        finally:
            session.close()

    # Agent operations
    def register_agent(self, agent_id: str, agent_name: str, agent_type: str) -> Agent:
        """Register an agent."""
        session = self.get_session()
        try:
            agent = session.query(Agent).filter_by(agent_id=agent_id).first()
            if agent:
                return agent

            agent = Agent(agent_id=agent_id, agent_name=agent_name, agent_type=agent_type)
            session.add(agent)
            session.commit()
            session.refresh(agent)
            return agent
        finally:
            session.close()

    def update_agent(self, agent_id: str, updates: Dict[str, Any]) -> Optional[Agent]:
        """Update agent info."""
        session = self.get_session()
        try:
            agent = session.query(Agent).filter_by(agent_id=agent_id).first()
            if not agent:
                return None

            for key, value in updates.items():
                if hasattr(agent, key):
                    setattr(agent, key, value)

            agent.last_active = _utc_now()
            session.commit()
            session.refresh(agent)
            return agent
        finally:
            session.close()

    def get_active_agents(self) -> List[Agent]:
        """
        Get agents with current assignments.

        Since we removed current_task_id from Agent model, we now query
        the tasks table for tasks with assignees, then join with agents.

        Returns:
            List of Agent objects that are currently assigned to tasks
        """
        session = self.get_session()
        try:
            # Get all unique agent IDs that are currently assigned to tasks
            assigned_agent_ids = session.query(Task.assignee).filter(
                Task.assignee.isnot(None)
            ).distinct().all()

            # Extract agent IDs from tuples
            agent_ids = [row[0] for row in assigned_agent_ids]

            if not agent_ids:
                return []

            # Get agent objects for these IDs
            return session.query(Agent).filter(Agent.agent_id.in_(agent_ids)).all()
        finally:
            session.close()

    # Statistics
    def get_statistics(self) -> Dict[str, int]:
        """Get task statistics."""
        session = self.get_session()
        try:
            all_tasks = session.query(Task).all()

            stats = {
                'total': len(all_tasks),
                'completed': 0,
                'todo': 0,
                'in_development': 0,
                'qa_fixing': 0,
                'security_fixing': 0,
                'in_qa': 0,
                'in_security': 0,
                'ready_for_qa': 0,
                'ready_for_security': 0,
                'qa_failed': 0,
                'security_failed': 0,
            }

            for task in all_tasks:
                if task.status == 'done':
                    stats['completed'] += 1
                elif task.status in stats:
                    stats[task.status] += 1

            return stats
        finally:
            session.close()

    # Metadata operations
    def set_metadata(self, key: str, value: Any):
        """Set project metadata value."""
        session = self.get_session()
        try:
            metadata = session.query(ProjectMetadata).filter_by(key=key).first()
            if metadata:
                metadata.set_value(value)
            else:
                metadata = ProjectMetadata(key=key)
                metadata.set_value(value)
                session.add(metadata)
            session.commit()
        finally:
            session.close()

    def get_metadata(self, key: str) -> Optional[Any]:
        """Get project metadata value."""
        session = self.get_session()
        try:
            metadata = session.query(ProjectMetadata).filter_by(key=key).first()
            return metadata.get_value() if metadata else None
        finally:
            session.close()
