"""
Agent Pool Management
=====================

Manages shared pool of concurrent agents across all types (dev/qa/sec).
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from pathlib import Path

from .config import get_agent_name


@dataclass
class AgentInfo:
    """Information about an active agent."""
    agent_id: str  # "developer_1", "qa", "sec_1", etc.
    agent_name: str  # "Maya", "Riley", "Morgan", etc.
    agent_type: str  # developer, qa, security
    current_task_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "current_task_id": self.current_task_id
        }


class AgentPool:
    """Manages shared pool of concurrent agents."""

    def __init__(self, max_concurrent: int = 5, config: Optional[dict] = None):
        """
        Initialize agent pool.

        Args:
            max_concurrent: Maximum number of concurrent agents (total across all types)
            config: Optional configuration dictionary (for agent names)
        """
        self.max_concurrent = max_concurrent
        self.config = config
        self.active_agents: Dict[str, AgentInfo] = {}  # agent_id -> AgentInfo

        # Counter for each agent type (wraps at max_concurrent)
        self.agent_counters = {
            'developer': 0,
            'qa': 0,
            'sec': 0
        }

    def get_available_slot(self) -> bool:
        """
        Check if pool has capacity for another agent.

        Returns:
            True if capacity available, False if pool is full
        """
        return len(self.active_agents) < self.max_concurrent

    def allocate_agent(self, agent_type: str, task_id: str) -> Optional[AgentInfo]:
        """
        Allocate an agent from the pool.

        Args:
            agent_type: Type of agent needed (developer, qa, sec)
            task_id: Task ID to assign to agent

        Returns:
            AgentInfo if allocated, None if pool is full
        """
        if not self.get_available_slot():
            return None

        # Get next available agent ID for this type
        index = self.agent_counters[agent_type]
        if index == 0:
            agent_id = agent_type
        else:
            agent_id = f"{agent_type}_{index}"

        # Increment counter for next allocation (wraps at max_concurrent)
        self.agent_counters[agent_type] = (index + 1) % self.max_concurrent

        # Get human-friendly name
        agent_name = get_agent_name(agent_id, self.config)

        # Create and track agent
        agent = AgentInfo(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_type=agent_type,
            current_task_id=task_id
        )

        self.active_agents[agent_id] = agent
        return agent

    def release_agent(self, agent_id: str):
        """
        Release agent back to pool.

        Args:
            agent_id: ID of agent to release
        """
        if agent_id in self.active_agents:
            del self.active_agents[agent_id]

    def update_agent_task(self, agent_id: str, task_id: Optional[str]):
        """
        Update agent's current task.

        Args:
            agent_id: ID of agent to update
            task_id: New task ID (or None to clear)
        """
        if agent_id in self.active_agents:
            self.active_agents[agent_id].current_task_id = task_id

    def get_active_count(self) -> int:
        """
        Get number of active agents.

        Returns:
            Count of active agents
        """
        return len(self.active_agents)

    def get_active_by_type(self) -> Dict[str, int]:
        """
        Get count of active agents per type.

        Returns:
            Dictionary mapping agent_type to count
        """
        counts = {'developer': 0, 'qa': 0, 'sec': 0}
        for agent in self.active_agents.values():
            if agent.agent_type in counts:
                counts[agent.agent_type] += 1
        return counts

    def get_active_agents(self) -> List[AgentInfo]:
        """
        Get all active agents.

        Returns:
            List of active AgentInfo objects
        """
        return list(self.active_agents.values())

    def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        """
        Get specific agent info.

        Args:
            agent_id: ID of agent to get

        Returns:
            AgentInfo if found, None otherwise
        """
        return self.active_agents.get(agent_id)

    def is_agent_active(self, agent_id: str) -> bool:
        """
        Check if specific agent is active.

        Args:
            agent_id: ID of agent to check

        Returns:
            True if agent is active, False otherwise
        """
        return agent_id in self.active_agents

    def get_capacity_info(self) -> Dict[str, int]:
        """
        Get capacity information.

        Returns:
            Dictionary with used, available, and total capacity
        """
        used = len(self.active_agents)
        return {
            'used': used,
            'available': self.max_concurrent - used,
            'total': self.max_concurrent
        }

    def clear(self):
        """Clear all agents from pool (for testing/reset)."""
        self.active_agents.clear()
        self.agent_counters = {
            'developer': 0,
            'qa': 0,
            'sec': 0
        }

    def __repr__(self) -> str:
        """String representation."""
        active_count = len(self.active_agents)
        return f"<AgentPool active={active_count}/{self.max_concurrent}>"
