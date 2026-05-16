"""
Relay Framework - Core Module
==============================

Multi-agent development framework with intelligent task orchestration.
"""

__version__ = "2.0.0"
__author__ = "Relay Framework Team"

# Core components
from .config import load_config, save_config, create_default_config, get_agent_name
from .database import TaskDatabase, Task, TaskLog, Agent, ProjectMetadata
from .agent_pool import AgentPool, AgentInfo
from .task_scheduler import TaskScheduler
from .status_generator import generate_status_dashboard
from .combined_planner import run_combined_planning
from .orchestrator import RelayOrchestrator
from .registry import (
    list_registered_projects,
    register_project,
    unregister_project,
    get_project_path,
)

__all__ = [
    # Version
    "__version__",
    "__author__",

    # Config
    "load_config",
    "save_config",
    "create_default_config",
    "get_agent_name",

    # Database
    "TaskDatabase",
    "Task",
    "TaskLog",
    "Agent",
    "ProjectMetadata",

    # Agent Pool
    "AgentPool",
    "AgentInfo",

    # Scheduler
    "TaskScheduler",

    # Status
    "generate_status_dashboard",

    # Combined Planner
    "run_combined_planning",

    # Orchestrator
    "RelayOrchestrator",

    # Registry
    "list_registered_projects",
    "register_project",
    "unregister_project",
    "get_project_path",
]
