"""
Task Scheduler
==============

Schedules tasks to available agents with dependency resolution and queuing.
"""

from typing import List, Optional, Dict
from pathlib import Path

from .database import TaskDatabase, Task
from .agent_pool import AgentPool, AgentInfo


class TaskScheduler:
    """Schedules tasks to available agents."""

    def __init__(self, db: TaskDatabase, pool: AgentPool, config: dict):
        """
        Initialize task scheduler.

        Args:
            db: Task database
            pool: Agent pool
            config: Configuration dictionary
        """
        self.db = db
        self.pool = pool
        self.config = config

    def get_required_agent_type(self, task_status: str) -> str:
        """
        Determine which agent type is needed for current task status.

        Args:
            task_status: Current status of the task

        Returns:
            Agent type needed (developer, qa, or sec)
        """
        if task_status in ['todo', 'qa_failed', 'security_failed']:
            return 'developer'
        elif task_status == 'ready_for_qa':
            return 'qa'
        elif task_status == 'ready_for_security':
            return 'sec'
        else:
            raise ValueError(f"Unexpected status: {task_status}")

    def can_task_start(self, task: Task) -> bool:
        """
        Check if task dependencies are resolved.

        Args:
            task: Task to check

        Returns:
            True if all dependencies are done, False otherwise
        """
        deps = task.get_dependencies()
        if not deps:
            return True

        # Check if all dependencies are done
        for dep_id in deps:
            dep_task = self.db.get_task(dep_id)
            if not dep_task or dep_task.status != "done":
                return False

        return True

    def get_ready_tasks(self) -> List[Task]:
        """
        Get all tasks that are ready to be worked on.

        Tasks are ready if:
        1. They need an agent (status: todo, ready_for_qa, ready_for_security, qa_failed, security_failed)
        2. Dependencies are resolved
        3. Not already assigned

        Returns:
            List of ready tasks, sorted by priority
        """
        ready_statuses = ['todo', 'ready_for_qa', 'ready_for_security', 'qa_failed', 'security_failed']
        ready_tasks = []

        for status in ready_statuses:
            tasks = self.db.get_tasks_by_status(status)
            for task in tasks:
                # Skip if already assigned
                if task.assignee:
                    continue

                # Check dependencies
                if self.can_task_start(task):
                    ready_tasks.append(task)

        # Sort by priority (higher first) and creation time
        ready_tasks.sort(key=lambda t: (-t.priority, t.created_at))
        return ready_tasks

    def get_queued_tasks(self) -> List[Task]:
        """
        Get tasks waiting for agents (pool full).

        Returns:
            List of tasks that would be scheduled if slots were available
        """
        ready_tasks = self.get_ready_tasks()

        # If pool not full, these aren't really queued
        if self.pool.get_available_slot():
            return []

        return ready_tasks

    def schedule_next_tasks(self) -> List[Task]:
        """
        Schedule ready tasks to available agent slots.

        Returns:
            List of tasks that were scheduled
        """
        scheduled = []

        while self.pool.get_available_slot():
            ready_tasks = self.get_ready_tasks()
            if not ready_tasks:
                break  # No more tasks ready

            # Get next task
            next_task = ready_tasks[0]

            # Determine agent type needed
            try:
                agent_type = self.get_required_agent_type(next_task.status)
            except ValueError:
                # Skip this task if status is invalid
                continue

            # Allocate agent
            agent = self.pool.allocate_agent(agent_type, next_task.id)
            if not agent:
                break  # Pool full (shouldn't happen, but safety check)

            # Assign agent to task
            self.db.update_task(next_task.id, {
                'assignee': agent.agent_id
            })

            # Register agent in database
            self.db.register_agent(agent.agent_id, agent.agent_name, agent.agent_type)
            self.db.update_agent(agent.agent_id, {
                'current_task_id': next_task.id
            })

            scheduled.append(next_task)

        return scheduled

    def release_agent_for_task(self, task_id: str):
        """
        Release agent assigned to a task.

        Args:
            task_id: Task ID to release agent from
        """
        task = self.db.get_task(task_id)
        if not task or not task.assignee:
            return

        agent_id = task.assignee

        # Release from pool
        self.pool.release_agent(agent_id)

        # Update database
        self.db.update_agent(agent_id, {
            'current_task_id': None,
            'tasks_completed': self.db.get_session().query(Task).filter_by(
                assignee=agent_id, status='done'
            ).count()
        })

        # Clear task assignee
        self.db.update_task(task_id, {'assignee': None})

    def get_queue_info(self) -> Dict[str, any]:
        """
        Get information about task queue.

        Returns:
            Dictionary with queue statistics
        """
        ready = self.get_ready_tasks()
        queued = self.get_queued_tasks()

        # Group by agent type needed
        by_type = {'developer': 0, 'qa': 0, 'sec': 0}
        for task in queued:
            try:
                agent_type = self.get_required_agent_type(task.status)
                by_type[agent_type] += 1
            except ValueError:
                pass

        return {
            'ready_count': len(ready),
            'queued_count': len(queued),
            'by_type': by_type,
            'pool_capacity': self.pool.get_capacity_info()
        }
