"""
Agent Spawner for Relay Framework Multi-Agent Orchestration

This module spawns and manages Claude Code CLI processes for executing tasks.
Each agent runs as an independent subprocess executing a specific task.
Agents are registered in the database for tracking and coordination.
"""

import subprocess
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional, List
from datetime import datetime
import os
import sys

# Add parent directory to path to import config and database
sys.path.insert(0, str(Path(__file__).parent))

from .config import (
    DEFAULT_AGENT_NAMES,
    get_model_id_for_agent,
    load_config,
    get_frontend_path,
    get_backend_path,
    get_path_info
)
from .database import TaskDatabase

logger = logging.getLogger(__name__)


class AgentSpawner:
    """
    Manages spawning and tracking of Claude Code CLI agent processes.

    Each agent is a subprocess running Claude Code CLI with a specific task prompt.
    The spawner tracks running agents, enforces concurrency limits, registers agents
    in the database, and handles cleanup on shutdown.
    """

    def __init__(self, project_dir: Path, db: TaskDatabase, max_concurrency: int = 5):
        """
        Initialize the agent spawner.

        Args:
            project_dir: Root directory of the project
            db: TaskDatabase instance for agent registration
            max_concurrency: Maximum number of agents to run concurrently
        """
        self.project_dir = Path(project_dir)
        self.db = db
        self.max_concurrency = max_concurrency
        self.running_agents: Dict[str, Tuple[subprocess.Popen, str, datetime, object]] = {}  # Added log_handle
        self.logs_dir = self.project_dir / ".relay" / "logs" / "agentlogs"

        # Create directories if they don't exist
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Pre-register all agents from config on startup
        self._initialize_agent_pool()

        logger.info(f"AgentSpawner initialized: project_dir={project_dir}, max_concurrency={max_concurrency}")

    def _initialize_agent_pool(self):
        """
        Pre-register all agents from config into the database.

        Creates agent records for all roles defined in DEFAULT_AGENT_NAMES.
        Each role has 5 agents: base name + _1 through _4.
        """
        from sqlalchemy import select
        from core.database import Agent

        # Define all agent roles (excluding ui_agent as it's on-demand)
        roles = ['frontend_developer', 'backend_developer', 'qa', 'security']

        with self.db.Session() as session:
            for role in roles:
                # Create base agent (e.g., "frontend_developer")
                agent_id = role
                agent_name = DEFAULT_AGENT_NAMES.get(agent_id, agent_id)

                # Check if agent already exists
                existing = session.execute(
                    select(Agent).where(Agent.agent_id == agent_id)
                ).scalar_one_or_none()

                if not existing:
                    new_agent = Agent(
                        agent_id=agent_id,
                        agent_name=agent_name,
                        agent_type=role,
                        tasks_completed=0,
                        created_at=datetime.now(),
                        last_active=datetime.now()
                    )
                    session.add(new_agent)
                    logger.info(f"Registered agent: {agent_id} ({agent_name})")

                # Create numbered agents (e.g., "frontend_developer_1" through "frontend_developer_4")
                for i in range(1, 5):
                    agent_id = f"{role}_{i}"
                    agent_name = DEFAULT_AGENT_NAMES.get(agent_id, agent_id)

                    # Check if agent already exists
                    existing = session.execute(
                        select(Agent).where(Agent.agent_id == agent_id)
                    ).scalar_one_or_none()

                    if not existing:
                        new_agent = Agent(
                            agent_id=agent_id,
                            agent_name=agent_name,
                            agent_type=role,
                            tasks_completed=0,
                            created_at=datetime.now(),
                            last_active=datetime.now()
                        )
                        session.add(new_agent)
                        logger.info(f"Registered agent: {agent_id} ({agent_name})")

            session.commit()

        logger.info("Agent pool initialized with all agents from config")

    def _get_agent_env(self) -> dict:
        """
        Get environment variables for agent subprocess.
        Configures project venv if available.

        Returns:
            Environment dict for subprocess
        """
        env = os.environ.copy()

        # Check for venv in project directory
        venv_dir = self.project_dir / ".relay" / "venv"
        if venv_dir.exists():
            venv_bin = venv_dir / "bin"
            venv_python = venv_bin / "python3"

            if venv_python.exists():
                # Set VIRTUAL_ENV to activate it
                env["VIRTUAL_ENV"] = str(venv_dir)

                # Prepend venv bin to PATH so python/pip commands use venv
                current_path = env.get("PATH", "")
                env["PATH"] = f"{venv_bin}:{current_path}"

                # Unset PYTHONHOME if set (can interfere with venv)
                env.pop("PYTHONHOME", None)

                logger.debug(f"Configured agent environment with venv: {venv_dir}")
        else:
            logger.warning("Venv not found at .relay/venv, agents will use system Python")

        return env

    def _get_available_agent(self, role: str) -> Optional[str]:
        """
        Get an available agent ID from the pre-registered pool for a given role.

        An agent is available if it's not currently assigned to any task.
        Checks the tasks table (tasks.assignee) instead of agents.current_task_id.

        Args:
            role: Agent role (frontend_developer, backend_developer, qa, security)

        Returns:
            Agent ID if available, None if all agents of this role are busy
        """
        from sqlalchemy import select
        from core.database import Agent, Task

        with self.db.Session() as session:
            # Get all agents of this role
            all_agents = session.execute(
                select(Agent.agent_id).where(Agent.agent_type == role)
            ).scalars().all()

            # Find first agent not assigned to any task
            for agent_id in all_agents:
                # Check if this agent is assigned to any task
                assigned_task = session.execute(
                    select(Task).where(Task.assignee == agent_id)
                ).scalar_one_or_none()

                if not assigned_task:
                    # This agent is available
                    return agent_id

        logger.debug(f"No available agents for role {role}")
        return None

    def _get_agent_name(self, agent_id: str) -> str:
        """
        Get human-readable agent name from config.

        Args:
            agent_id: Agent ID (e.g., "developer", "developer_1")

        Returns:
            Human-readable name (e.g., "Stacey", "Maya")
        """
        return DEFAULT_AGENT_NAMES.get(agent_id, agent_id)

    def _get_agent_working_directory(self, role: str) -> Path:
        """
        Get the appropriate working directory for an agent based on their role.

        Frontend developers work in the frontend directory.
        Backend developers work in the backend directory.
        QA and Security agents work in the project root.

        Args:
            role: Agent role (frontend_developer, backend_developer, qa, security)

        Returns:
            Path to the working directory
        """
        try:
            config = load_config(self.project_dir)

            if role == 'frontend_developer':
                frontend_path = get_frontend_path(self.project_dir, config)
                if frontend_path and frontend_path.exists():
                    logger.debug(f"Frontend developer will work in: {frontend_path}")
                    return frontend_path
                else:
                    logger.warning(f"Frontend path not configured or doesn't exist, using project root")

            elif role == 'backend_developer':
                backend_path = get_backend_path(self.project_dir, config)
                if backend_path and backend_path.exists():
                    logger.debug(f"Backend developer will work in: {backend_path}")
                    return backend_path
                else:
                    logger.warning(f"Backend path not configured or doesn't exist, using project root")

        except FileNotFoundError:
            logger.warning("Config not found, agents will work in project root")

        # Default: project root for QA, Security, or if paths not configured
        return self.project_dir

    def _build_agent_context(self, role: str) -> str:
        """
        Build context information to prepend to agent prompts.

        Provides agents with information about project structure, their working
        directory, and relevant paths based on their role.

        Args:
            role: Agent role

        Returns:
            Context string to prepend to prompt
        """
        try:
            config = load_config(self.project_dir)
            context_parts = []

            # Add project info
            if 'project' in config:
                project_name = config['project'].get('name', 'Unknown')
                project_type = config['project'].get('type', 'Unknown')
                context_parts.append(f"Project: {project_name} ({project_type})")

            # Add path information based on role
            if role == 'frontend_developer':
                frontend_info = get_path_info(self.project_dir, 'frontend', config)
                if frontend_info:
                    context_parts.append(f"\nYour working directory: {frontend_info['path']}")
                    if frontend_info.get('framework'):
                        context_parts.append(f"Frontend framework: {frontend_info['framework']}")
                    if frontend_info.get('dev_command'):
                        context_parts.append(f"Dev command: {frontend_info['dev_command']}")
                    if frontend_info.get('build_command'):
                        context_parts.append(f"Build command: {frontend_info['build_command']}")

                    # Add critical dependency warnings
                    context_parts.append("\n⚠️  CRITICAL: Verify all packages in config files are installed!")
                    if frontend_info.get('framework') == 'vite-react':
                        context_parts.append("   - Tailwind CSS v4 requires @tailwindcss/postcss package")
                        context_parts.append("   - All PostCSS plugins must be in package.json devDependencies")
                        context_parts.append("   - Check postcss.config.js matches installed packages")

            elif role == 'backend_developer':
                backend_info = get_path_info(self.project_dir, 'backend', config)
                if backend_info:
                    context_parts.append(f"\nYour working directory: {backend_info['path']}")
                    if backend_info.get('framework'):
                        context_parts.append(f"Backend framework: {backend_info['framework']}")
                    if backend_info.get('dev_command'):
                        context_parts.append(f"Dev command: {backend_info['dev_command']}")
                    if backend_info.get('build_command'):
                        context_parts.append(f"Build command: {backend_info['build_command']}")

            elif role in ['qa', 'security']:
                # QA and Security agents need info about both frontend and backend
                frontend_info = get_path_info(self.project_dir, 'frontend', config)
                backend_info = get_path_info(self.project_dir, 'backend', config)

                if frontend_info:
                    context_parts.append(f"\nFrontend: {frontend_info['path']}")
                    if frontend_info.get('framework'):
                        context_parts.append(f"  Framework: {frontend_info['framework']}")

                if backend_info:
                    context_parts.append(f"Backend: {backend_info['path']}")
                    if backend_info.get('framework'):
                        context_parts.append(f"  Framework: {backend_info['framework']}")

                # Add critical checks for QA
                if role == 'qa' and frontend_info:
                    context_parts.append("\n⚠️  QA CRITICAL CHECKS:")
                    context_parts.append("   - For UI tasks: Verify styling is loading (not unstyled pages)")
                    context_parts.append("   - Check package.json has all dependencies from config files")
                    context_parts.append("   - Run 'npm run build' BEFORE functional testing")

            if context_parts:
                return "=== PROJECT CONTEXT ===\n" + "\n".join(context_parts) + "\n" + "="*50 + "\n\n"

        except FileNotFoundError:
            logger.debug("No config found, skipping context")

        return ""

    def _register_agent_in_db(self, agent_id: str, agent_type: str, task_id: str):
        """
        Update agent last_active timestamp when assigned a task.
        NOTE: Task assignment is tracked in tasks.assignee, not here.

        Args:
            agent_id: Agent ID from pool
            agent_type: Agent type (frontend_developer, backend_developer, qa, security, ui_agent)
            task_id: Task being assigned to this agent
        """
        agent_name = self._get_agent_name(agent_id)

        from sqlalchemy import select, update
        from core.database import Agent

        with self.db.Session() as session:
            # UI agents are temporary, create on-demand
            if agent_type == "ui_agent":
                existing = session.execute(
                    select(Agent).where(Agent.agent_id == agent_id)
                ).scalar_one_or_none()

                if not existing:
                    new_agent = Agent(
                        agent_id=agent_id,
                        agent_name=agent_name,
                        agent_type=agent_type,
                        tasks_completed=0,
                        created_at=datetime.now(),
                        last_active=datetime.now()
                    )
                    session.add(new_agent)
                    session.commit()
                    logger.info(f"Created temporary UI agent {agent_id} for task {task_id}")
                    return

            # For pool agents, just update last_active
            # Task assignment is tracked in tasks.assignee field
            result = session.execute(
                update(Agent)
                .where(Agent.agent_id == agent_id)
                .values(last_active=datetime.now())
            )

            if result.rowcount == 0:
                logger.error(f"Agent {agent_id} not found in pool! This should not happen.")
                raise RuntimeError(f"Agent {agent_id} not in pre-registered pool")

            session.commit()
            logger.info(f"Assigned task {task_id} to agent {agent_id} ({agent_name})")

    def _unregister_agent_from_db(self, agent_id: str):
        """
        Update agent stats after task completion.
        - For pool agents: Increment tasks_completed
        - For UI agents: Delete the temporary record
        NOTE: Task assignment is tracked in tasks.assignee, which should be NULL by now.

        Args:
            agent_id: Agent ID
        """
        from sqlalchemy import select, update, delete
        from core.database import Agent

        with self.db.Session() as session:
            # Get current agent
            agent = session.execute(
                select(Agent).where(Agent.agent_id == agent_id)
            ).scalar_one_or_none()

            if not agent:
                logger.warning(f"Agent {agent_id} not found in database")
                return

            # UI agents are temporary - delete them
            if agent.agent_type == "ui_agent":
                session.execute(
                    delete(Agent).where(Agent.agent_id == agent_id)
                )
                session.commit()
                logger.debug(f"Deleted temporary UI agent {agent_id}")
            else:
                # Pool agents - increment completed count
                # Task should have already been freed (assignee set to NULL) by the agent itself
                session.execute(
                    update(Agent)
                    .where(Agent.agent_id == agent_id)
                    .values(
                        last_active=datetime.now(),
                        tasks_completed=agent.tasks_completed + 1
                    )
                )
                session.commit()
                logger.debug(f"Updated agent {agent_id} stats (completed tasks: {agent.tasks_completed + 1})")

    def spawn_agent(self, role: str, task_id: str, prompt: str) -> Tuple[bool, Optional[str]]:
        """
        Spawn a new Claude Code CLI agent for a task.

        Args:
            role: Role of the agent (frontend_developer, backend_developer, qa, security, ui_agent)
            task_id: Unique task identifier
            prompt: Full prompt text for the agent

        Returns:
            Tuple of (success: bool, agent_id: str or None)
            Returns (False, None) if at max concurrency
            Returns (True, agent_id) if spawned successfully
        """
        # Check if task already has an ACTIVE agent assigned
        for agent_id, (process, assigned_task_id, _, _) in self.running_agents.items():
            if assigned_task_id == task_id:
                # Check if process is actually still running
                if process.poll() is None:
                    # Process is still alive - this is a real conflict
                    logger.warning(f"Cannot spawn agent for task {task_id}: already has active agent {agent_id} assigned (PID: {process.pid})")
                    return False, None
                else:
                    # Process has exited but hasn't been reaped yet - not a real conflict
                    logger.debug(f"Agent {agent_id} for task {task_id} has exited (exit_code: {process.poll()}) but not yet reaped - allowing new agent spawn")

        # Check concurrency limit
        if len(self.running_agents) >= self.max_concurrency:
            logger.warning(f"Cannot spawn agent for task {task_id}: at max concurrency ({self.max_concurrency})")
            return False, None

        # Get agent ID
        if role == "ui_agent":
            # UI agents are on-demand, generate temporary ID
            agent_id = f"ui_agent_{task_id}"
            agent_name = "UI Agent"
        else:
            # Get an available agent from the pre-registered pool
            agent_id = self._get_available_agent(role)
            if not agent_id:
                logger.warning(f"Cannot spawn agent for task {task_id}: no available agents for role {role}")
                return False, None
            agent_name = self._get_agent_name(agent_id)

        try:
            # Register agent in database
            self._register_agent_in_db(agent_id, role, task_id)

            # Get appropriate working directory for this role
            working_dir = self._get_agent_working_directory(role)

            # Build context information for the agent
            context = self._build_agent_context(role)

            # Prepend context to prompt
            full_prompt = agent_name + ": " + task_id + " (" + role + ")\n" + context + prompt

            # Prepare log file for agent output
            log_file = self.logs_dir / f"agent_{agent_id}_{task_id}.log"
            log_handle = open(log_file, 'w')

            # Get model ID for this role
            model_id = get_model_id_for_agent(role)

            # Build Claude CLI command with --print mode and prompt
            # Use --print for non-interactive execution with stdin
            command = [
                "claude",
                "--model", model_id,
                "--dangerously-skip-permissions",  # Auto-approve tools for automated agents
                "--print",  # Non-interactive mode that accepts stdin
            ]

            logger.info(f"Spawning agent {agent_id} ({agent_name}) for task {task_id} (model: {model_id}) in {working_dir}")

            # Get environment with venv configured
            agent_env = self._get_agent_env()

            # Spawn the subprocess with stdin pipe
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(working_dir),  # Use role-specific working directory
                env=agent_env,  # Use custom environment with venv
                # Make the process independent so it can continue if parent dies
                preexec_fn=os.setpgrp if os.name != 'nt' else None
            )

            # Send prompt via stdin
            try:
                process.stdin.write(full_prompt)
                process.stdin.flush()
                process.stdin.close()
            except Exception as e:
                logger.error(f"Failed to write prompt to stdin: {e}")
                process.kill()
                self._unregister_agent_from_db(agent_id)
                return False, None

            # Track the running agent (including log handle for cleanup)
            self.running_agents[agent_id] = (process, task_id, datetime.now(), log_handle)

            logger.info(f"Agent {agent_id} ({agent_name}) spawned successfully (PID: {process.pid}, task: {task_id})")
            return True, agent_id

        except Exception as e:
            logger.error(f"Failed to spawn agent for task {task_id}: {e}", exc_info=True)
            self._unregister_agent_from_db(agent_id)
            return False, None

    def get_running_agents(self) -> List[str]:
        """
        Get list of currently running agent IDs.

        Returns:
            List of agent IDs
        """
        return list(self.running_agents.keys())

    def get_agent_count_by_role(self, role: str) -> int:
        """
        Count how many agents of a specific role are currently running.

        Args:
            role: Role to count (frontend_developer, backend_developer, qa, security, ui_agent)

        Returns:
            Number of running agents with this role
        """
        count = 0
        for agent_id in self.running_agents.keys():
            # Check if agent_id starts with role (handles "developer", "developer_1", etc.)
            if agent_id == role or agent_id.startswith(f"{role}_"):
                count += 1
        return count

    def check_completed_agents(self) -> List[Tuple[str, str, int, str]]:
        """
        Non-blocking check for completed agents.

        Polls all running agents to see if any have finished.
        Collects their output and removes them from tracking.

        Returns:
            List of tuples: (agent_id, task_id, exit_code, output)
        """
        completed = []
        to_remove = []

        for agent_id, (process, task_id, started_at, log_handle) in self.running_agents.items():
            # Non-blocking poll
            exit_code = process.poll()

            if exit_code is not None:
                # Agent has finished
                elapsed = (datetime.now() - started_at).total_seconds()

                # Close log file handle if still open
                try:
                    if log_handle and not log_handle.closed:
                        log_handle.close()
                except Exception as e:
                    logger.warning(f"Error closing log handle for agent {agent_id}: {e}")

                # Read output from log file
                log_file = self.logs_dir / f"agent_{agent_id}_{task_id}.log"
                try:
                    output = log_file.read_text()
                except Exception as e:
                    output = f"Error reading log file: {e}"

                logger.info(f"Agent {agent_id} completed (task: {task_id}, exit_code: {exit_code}, elapsed: {elapsed:.1f}s)")

                # Unregister agent from database
                self._unregister_agent_from_db(agent_id)

                completed.append((agent_id, task_id, exit_code, output))
                to_remove.append(agent_id)

        # Remove completed agents from tracking
        for agent_id in to_remove:
            del self.running_agents[agent_id]

        return completed

    def wait_for_agent(self, agent_id: str, timeout: Optional[float] = None) -> Tuple[Optional[int], Optional[str]]:
        """
        Blocking wait for a specific agent to complete.

        Args:
            agent_id: Agent ID to wait for
            timeout: Optional timeout in seconds

        Returns:
            Tuple of (exit_code, output) or (None, None) if agent not found
        """
        if agent_id not in self.running_agents:
            logger.warning(f"Cannot wait for agent {agent_id}: not found in running agents")
            return None, None

        process, task_id, started_at, log_handle = self.running_agents[agent_id]

        try:
            logger.info(f"Waiting for agent {agent_id} (task: {task_id}, timeout: {timeout})")
            exit_code = process.wait(timeout=timeout)
            elapsed = (datetime.now() - started_at).total_seconds()

            # Close log file handle if still open
            try:
                if log_handle and not log_handle.closed:
                    log_handle.close()
            except Exception as e:
                logger.warning(f"Error closing log handle for agent {agent_id}: {e}")

            # Read output from log file
            log_file = self.logs_dir / f"agent_{agent_id}_{task_id}.log"
            try:
                output = log_file.read_text()
            except Exception as e:
                output = f"Error reading log file: {e}"

            logger.info(f"Agent {agent_id} completed (exit_code: {exit_code}, elapsed: {elapsed:.1f}s)")

            # Unregister agent from database
            self._unregister_agent_from_db(agent_id)

            # Remove from tracking
            del self.running_agents[agent_id]

            return exit_code, output

        except subprocess.TimeoutExpired:
            logger.warning(f"Agent {agent_id} timed out after {timeout}s")
            return None, None
        except Exception as e:
            logger.error(f"Error waiting for agent {agent_id}: {e}", exc_info=True)
            return None, None

    def get_agent_info(self, agent_id: str) -> Optional[Dict]:
        """
        Get information about a running agent.

        Args:
            agent_id: Agent ID to query

        Returns:
            Dict with agent info or None if not found
        """
        if agent_id not in self.running_agents:
            return None

        process, task_id, started_at, _ = self.running_agents[agent_id]
        elapsed = (datetime.now() - started_at).total_seconds()

        return {
            "agent_id": agent_id,
            "agent_name": self._get_agent_name(agent_id),
            "task_id": task_id,
            "pid": process.pid,
            "started_at": started_at.isoformat(),
            "elapsed_seconds": elapsed,
            "is_running": process.poll() is None
        }

    def terminate_agent(self, agent_id: str):
        """
        Terminate a specific agent process.

        Used when agent was spawned but task claim failed due to race condition.
        Immediately kills the process and cleans up resources.

        Args:
            agent_id: Agent ID to terminate
        """
        if agent_id not in self.running_agents:
            logger.warning(f"Cannot terminate {agent_id}: not in running_agents")
            return

        process, task_id, start_time, log_handle = self.running_agents[agent_id]

        try:
            logger.info(f"Terminating agent {agent_id} (PID: {process.pid}, task: {task_id})")

            # First try graceful termination
            process.terminate()
            try:
                process.wait(timeout=5)  # Wait up to 5 seconds for graceful shutdown
                logger.info(f"Agent {agent_id} terminated gracefully")
            except subprocess.TimeoutExpired:
                # Force kill if didn't terminate gracefully
                logger.warning(f"Agent {agent_id} did not terminate gracefully, killing")
                process.kill()
                process.wait()
                logger.info(f"Agent {agent_id} force killed")

        except Exception as e:
            logger.error(f"Error terminating agent {agent_id}: {e}", exc_info=True)

        finally:
            # Cleanup resources
            try:
                if log_handle and not log_handle.closed:
                    log_handle.close()
            except Exception as e:
                logger.warning(f"Error closing log handle for agent {agent_id}: {e}")

            # Remove from tracking
            if agent_id in self.running_agents:
                del self.running_agents[agent_id]

            # Unregister from database
            self._unregister_agent_from_db(agent_id)

            logger.info(f"Agent {agent_id} terminated and cleaned up")

    def terminate_all(self, timeout: float = 10.0):
        """
        Gracefully terminate all running agents.

        First sends SIGTERM, waits for timeout, then sends SIGKILL if needed.

        Args:
            timeout: Seconds to wait for graceful termination before force kill
        """
        if not self.running_agents:
            logger.info("No running agents to terminate")
            return

        logger.info(f"Terminating {len(self.running_agents)} running agents...")

        # Send SIGTERM to all agents
        for agent_id, (process, task_id, _, log_handle) in self.running_agents.items():
            try:
                logger.info(f"Sending SIGTERM to agent {agent_id} (PID: {process.pid})")
                process.terminate()
                # Close log handle
                if log_handle and not log_handle.closed:
                    log_handle.close()
            except Exception as e:
                logger.error(f"Error terminating agent {agent_id}: {e}")

        # Wait for graceful termination
        import time
        start_time = time.time()
        while self.running_agents and (time.time() - start_time) < timeout:
            time.sleep(0.5)
            # Check for completed agents
            self.check_completed_agents()

        # Force kill any remaining agents
        if self.running_agents:
            logger.warning(f"Force killing {len(self.running_agents)} agents that didn't terminate gracefully")
            for agent_id, (process, task_id, _, log_handle) in list(self.running_agents.items()):
                try:
                    logger.warning(f"Sending SIGKILL to agent {agent_id} (PID: {process.pid})")
                    process.kill()
                    # Close log handle
                    if log_handle and not log_handle.closed:
                        log_handle.close()
                    self._unregister_agent_from_db(agent_id)
                except Exception as e:
                    logger.error(f"Error force killing agent {agent_id}: {e}")

            # Clear all running agents
            self.running_agents.clear()

        logger.info("All agents terminated")
