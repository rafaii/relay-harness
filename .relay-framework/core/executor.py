"""
Executor for SECTION 2: Execution Loop
======================================

Manages the main execution loop for task completion with:
- Developer agents (frontend/backend) spawning for pending tasks
- QA gate for completed tasks
- Security gate for QA-passed tasks
- Browser verification for frontend tasks (validates against ui_standards.md)
- Task status tracking and baton mechanism
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from sqlalchemy import update as sql_update

from core.database import TaskDatabase, Task
from core.agent_spawner import AgentSpawner
from core.cli_dashboard import CLIDashboard, AgentDisplay

logger = logging.getLogger(__name__)

# Active work states for dashboard filtering
# Only show agents whose tasks are actively being worked on
ACTIVE_WORK_STATES = {
    'in_development',
    'in_qa',
    'in_security',
    'qa_fixing',
    'security_fixing'
}


class Executor:
    """
    Manages SECTION 2 execution loop.

    Responsibilities:
    - Poll for completed agents
    - Process QA gate for dev_complete tasks
    - Process Security gate for QA-passed tasks
    - Spawn developer agents for ready tasks
    - Update task dashboard
    - Handle graceful shutdown
    """

    def __init__(
        self,
        project_dir: Path,
        db: TaskDatabase,
        spawner: AgentSpawner,
        max_concurrency: int = 5,
        use_dashboard: bool = True
    ):
        """
        Initialize executor.

        Args:
            project_dir: Project directory
            db: TaskDatabase instance
            spawner: AgentSpawner instance
            max_concurrency: Maximum concurrent agents
            use_dashboard: Enable real-time CLI dashboard
        """
        self.project_dir = Path(project_dir)
        self.db = db
        self.spawner = spawner
        self.max_concurrency = max_concurrency
        self.shutdown_requested = False
        self.use_dashboard = use_dashboard
        self.dashboard = CLIDashboard() if use_dashboard else None

        logger.info(f"Executor initialized: project_dir={project_dir}, max_concurrency={max_concurrency}")

    def shutdown(self):
        """Request shutdown and terminate all agents."""
        logger.info("Shutdown requested")
        self.shutdown_requested = True
        self.spawner.terminate_all()

    async def execute(self):
        """
        Main execution loop.

        Loop until all tasks are completed or shutdown is requested:
        1. Check for completed agents
        2. Process QA gate
        3. Process Security gate
        4. Spawn agents for ready tasks
        5. Update dashboard
        6. Sleep
        """
        logger.info("Starting SECTION 2 execution loop")

        # Start the dashboard
        if self.dashboard:
            self.dashboard.start()

        iteration = 0

        try:
            while not self.shutdown_requested:
                iteration += 1
                logger.debug(f"Execution loop iteration {iteration}")

                try:
                    # 1. Check for completed agents
                    completed = self.spawner.check_completed_agents()
                    if completed:
                        await self._handle_completed_agents(completed)

                    # 1.4. Check for tasks needing escalation
                    self._check_escalations()

                    # 1.5. Recover tasks with stale assignees
                    self._recover_stuck_assignees()

                    # 1.6. Terminate slow-exit processes (released baton but still running >15s)
                    self._terminate_slow_exit_processes()

                    # 2. Process QA gate
                    await self._process_qa_gate()

                    # 3. Process Security gate
                    await self._process_security_gate()

                    # 3.5. Check if DevOps phase should be triggered
                    self._check_devops_trigger()

                    # 4. Check if all tasks are completed
                    if self._all_tasks_complete():
                        logger.info("All tasks completed!")
                        break

                    # 5. Spawn agents for ready tasks
                    ready_tasks = self._get_ready_tasks()
                    if ready_tasks:
                        await self._spawn_agents_for_tasks(ready_tasks)

                    # 6. Update CLI dashboard (real-time)
                    if self.dashboard:
                        self._update_cli_dashboard()

                    # 7. Update file dashboard (for reference)
                    self._update_dashboard()

                    # 8. Sleep before next iteration
                    await asyncio.sleep(2)

                except Exception as e:
                    logger.error(f"Error in execution loop: {e}", exc_info=True)
                    await asyncio.sleep(5)

        finally:
            # Stop the dashboard
            if self.dashboard:
                self.dashboard.stop()

            logger.info("Execution loop completed")

    async def _handle_completed_agents(self, completed: List[tuple]):
        """
        Handle completed agents.

        Args:
            completed: List of tuples (agent_id, task_id, exit_code, output)
        """
        for agent_id, task_id, exit_code, output in completed:
            logger.info(f"Handling completed agent {agent_id} for task {task_id} (exit_code: {exit_code})")

            # Get task
            task = self.db.get_task(task_id)
            if not task:
                logger.warning(f"Task {task_id} not found for completed agent {agent_id}")
                continue

            # Determine agent role from agent_id
            agent_role = None
            if ('frontend_developer' in agent_id or 'backend_developer' in agent_id or
                'database' in agent_id or 'ui_designer' in agent_id or 'devops' in agent_id):
                agent_role = 'developer'
            elif 'qa' in agent_id:
                agent_role = 'qa'
            elif 'security' in agent_id:
                agent_role = 'security'

            # Check exit code
            if exit_code == 0:
                # Only update status for DEVELOPER agents
                # QA and Security agents set their own status before exiting
                if agent_role == 'developer':
                    # Success - mark as ready_for_qa
                    self.db.update_task(task_id, {
                        "status": "ready_for_qa",
                        "assignee": None
                    })

                    # Log completion
                    self.db.log_action(
                        task_id=task_id,
                        agent_id=agent_id,
                        action="completed",
                        notes="Development completed successfully, ready for QA"
                    )

                    logger.info(f"Task {task_id} marked as ready_for_qa")

                    # Check if migration needed for backend tasks
                    if 'backend_developer' in agent_id:
                        await self._check_and_create_migration_task(task)

                else:
                    # QA/Security agent completed - they already set the status
                    # Just clear the assignee if not already cleared
                    if task.assignee == agent_id:
                        self.db.update_task(task_id, {"assignee": None})
                        logger.info(f"{agent_role.upper()} agent {agent_id} completed task {task_id} - assignee cleared")
                    else:
                        logger.info(f"{agent_role.upper()} agent {agent_id} completed task {task_id} - status already set by agent")

            else:
                # Failure - only mark as failed for DEVELOPER agents
                # QA/Security agents may exit with non-zero to signal issues but status is already set
                if agent_role == 'developer':
                    # Failure - mark as failed and log error
                    self.db.update_task(task_id, {
                        "status": "failed",
                        "assignee": None
                    })

                    # Log failure
                    self.db.log_action(
                        task_id=task_id,
                        agent_id=agent_id,
                        action="failed",
                        status="failed",
                        notes=f"Agent failed with exit code {exit_code}. Check logs for details."
                    )

                    logger.error(f"Task {task_id} failed (exit_code: {exit_code})")
                else:
                    # QA/Security agent exited with error - just clear assignee
                    if task.assignee == agent_id:
                        self.db.update_task(task_id, {"assignee": None})
                    logger.warning(f"{agent_role.upper()} agent {agent_id} exited with code {exit_code} for task {task_id}")

                    # Log the exit
                    self.db.log_action(
                        task_id=task_id,
                        agent_id=agent_id,
                        action="agent_error",
                        status="failed",
                        notes=f"{agent_role.upper()} agent exited with code {exit_code}. Check logs for details."
                    )

            # DEFENSIVE: Always ensure assignee is cleared when agent completes
            # This is a safety net in case the agent didn't properly release the baton
            task_check = self.db.get_task(task_id)
            if task_check and task_check.assignee == agent_id:
                logger.warning(
                    f"Force-clearing assignee for task {task_id} - "
                    f"agent {agent_id} completed but baton wasn't released"
                )
                self.db.update_task(task_id, {"assignee": None})

    def _check_devops_trigger(self):
        """
        Check if DevOps phase should be triggered.

        When all development tasks (architecture, core_features, additional_features)
        are complete, automatically create DevOps tasks for deployment setup.
        """
        try:
            # Check if DevOps tasks already exist
            session = self.db.get_session()
            try:
                from core.database import Task

                existing_devops = session.query(Task).filter(
                    Task.phase == "devops"
                ).first()

                if existing_devops:
                    # DevOps phase already created
                    return

                # Check if development phases are complete
                dev_phases = ["architecture", "core_features", "additional_features"]
                all_dev_complete = True

                for phase in dev_phases:
                    phase_tasks = session.query(Task).filter(
                        Task.phase == phase
                    ).all()

                    if not phase_tasks:
                        # Phase doesn't exist, skip
                        continue

                    # Check if all tasks in phase are done
                    incomplete = [t for t in phase_tasks if t.status != "done"]
                    if incomplete:
                        all_dev_complete = False
                        break

                if not all_dev_complete:
                    # Development not complete yet
                    return

                # All development complete - create DevOps tasks
                logger.info("Development phases complete! Creating DevOps phase...")

                devops_tasks = [
                    {
                        "id": "DEVOPS-001",
                        "title": "Create Dockerfile for application",
                        "description": """Create Docker containerization setup for the application.

**Requirements:**
1. Review project structure and tech stack from docs/system_design.md
2. Create Dockerfile(s):
   - Frontend: If separate frontend app, create frontend/Dockerfile
   - Backend: Create backend/Dockerfile or root Dockerfile
   - Multi-stage builds for optimization

3. Dockerfile must include:
   - Appropriate base image (node:18-alpine, python:3.11-slim, etc.)
   - Dependency installation
   - Build steps
   - Production optimizations (layer caching, minimal image size)
   - Non-root user for security
   - Health check endpoint

4. Create .dockerignore to exclude:
   - node_modules, .git, .env, logs, temp files
   - Development-only files

5. Create docker-compose.yml for local development:
   - Application service(s)
   - Database service (if needed)
   - Volume mounts for development
   - Environment variables
   - Network configuration

6. Test locally:
   - Build images successfully
   - Run containers
   - Verify application works
   - Check image size (optimize if >500MB)

**Acceptance Criteria:**
- Dockerfile builds without errors
- Application runs in container
- docker-compose up starts all services
- Documentation in README for Docker usage

References: docs/system_design.md
""",
                        "phase": "devops",
                        "role": "devops_developer",
                        "agent_type": "devops",
                        "dependencies": [],
                        "priority": 0,
                        "complexity": 3,
                        "status": "todo"
                    },
                    {
                        "id": "DEVOPS-002",
                        "title": "Setup CI/CD pipeline",
                        "description": """Create continuous integration and deployment pipeline.

**Requirements:**
1. Choose CI/CD platform:
   - GitHub Actions (if on GitHub)
   - GitLab CI (if on GitLab)
   - CircleCI, Travis, Jenkins (alternatives)

2. Create workflow files:
   - `.github/workflows/ci.yml` (for GitHub Actions)
   - Or equivalent for chosen platform

3. CI pipeline must include:
   - Checkout code
   - Install dependencies
   - Run linters/formatters
   - Run tests
   - Build application
   - Security scanning (npm audit, Snyk, etc.)

4. CD pipeline (optional, for staging):
   - Deploy to staging environment
   - Run smoke tests
   - Notify on deployment

5. Pipeline triggers:
   - On pull request: Run CI only
   - On push to main: Run CI + CD
   - Manual trigger option

6. Test the pipeline:
   - Create test PR
   - Verify all checks pass
   - Fix any failures

**Acceptance Criteria:**
- CI pipeline runs on every PR
- All checks (lint, test, build) must pass
- Clear status badges in README
- Documentation for running locally

References: docs/system_design.md
""",
                        "phase": "devops",
                        "role": "devops_developer",
                        "agent_type": "devops",
                        "dependencies": ["DEVOPS-001"],
                        "priority": 0,
                        "complexity": 3,
                        "status": "todo"
                    },
                    {
                        "id": "DEVOPS-003",
                        "title": "Create environment configuration files",
                        "description": """Setup environment configuration for different deployment environments.

**Requirements:**
1. Create environment templates:
   - `.env.example` - Template with all required vars
   - `.env.development` - Local development defaults
   - `.env.production.template` - Production template

2. Document all environment variables in README:
   - Variable name
   - Purpose
   - Default value (if any)
   - Required vs optional
   - Example values

3. Setup environment loading:
   - Use dotenv or equivalent
   - Validate required env vars on startup
   - Provide clear error messages for missing vars

4. Security considerations:
   - Never commit actual .env files
   - Add .env to .gitignore
   - Use secrets management for production (AWS Secrets Manager, etc.)
   - Document secret rotation process

5. Environment-specific configs:
   - Database URLs
   - API keys (examples only)
   - Feature flags
   - Logging levels
   - CORS settings
   - Port numbers

**Acceptance Criteria:**
- .env.example complete with all variables
- Clear documentation in README
- Application fails fast with clear errors if env vars missing
- No secrets committed to git

References: docs/system_design.md, docs/security_policy.md
""",
                        "phase": "devops",
                        "role": "devops_developer",
                        "agent_type": "devops",
                        "dependencies": [],
                        "priority": 0,
                        "complexity": 2,
                        "status": "todo"
                    }
                ]

                for task_data in devops_tasks:
                    self.db.create_task(task_data)
                    logger.info(f"Created DevOps task: {task_data['id']}")

                logger.info(f"✅ Created {len(devops_tasks)} DevOps tasks")

            finally:
                session.close()

        except Exception as e:
            logger.error(f"Failed to check DevOps trigger: {e}")

    def _check_escalations(self):
        """
        Check for tasks that need escalation after repeated failures.

        If a task has failed QA or Security multiple times, escalate to
        manual review.
        """
        try:
            from core.escalation import TaskEscalation

            escalation = TaskEscalation(self.project_dir)

            # Get tasks that have failed QA or Security
            session = self.db.get_session()
            try:
                from core.database import Task

                failed_tasks = session.query(Task).filter(
                    Task.status.in_(["qa_failed", "security_failed"])
                ).all()

                for task in failed_tasks:
                    # Check failure count
                    failure_info = escalation.check_failure_count(task.id, self.db)

                    if failure_info["should_escalate"]:
                        logger.warning(
                            f"Task {task.id} has failed {failure_info['total_failures']} times - escalating"
                        )
                        review_task_id = escalation.escalate_task(task.id, failure_info, self.db)

                        if review_task_id:
                            logger.info(f"Created review task: {review_task_id}")

            finally:
                session.close()

        except Exception as e:
            logger.error(f"Failed to check escalations: {e}")

    def _recover_stuck_assignees(self):
        """
        Clear assignee field for tasks where agent process no longer exists.

        This prevents tasks from being permanently stuck when:
        - An agent crashes before releasing the baton (setting assignee=NULL)
        - There's a race condition during status update
        - An agent times out without cleanup

        Runs on every execution loop iteration to ensure tasks don't get blocked.
        """
        session = self.db.get_session()
        try:
            from core.database import Task

            # Get all tasks with assignee set
            tasks_with_assignees = session.query(Task).filter(
                Task.assignee.isnot(None)
            ).all()

            for task in tasks_with_assignees:
                # Check if agent still exists in running_agents
                if task.assignee not in self.spawner.running_agents:
                    # Agent is gone but assignee wasn't cleared - this is a stale assignment
                    logger.warning(
                        f"Recovering task {task.id} from stale assignee: {task.assignee} "
                        f"(status: {task.status})"
                    )
                    task.assignee = None
                    session.commit()

                    # Log recovery action
                    self.db.log_action(
                        task_id=task.id,
                        agent_id="system",
                        action="recovered",
                        notes=f"Cleared stale assignee {task.assignee} - agent no longer running"
                    )

        except Exception as e:
            logger.error(f"Error recovering stuck assignees: {e}", exc_info=True)
        finally:
            session.close()

    def _terminate_slow_exit_processes(self):
        """
        Force-terminate agent processes taking too long to exit after releasing baton.

        Agents may take 30s-2min to naturally exit after updating database.
        This watchdog force-kills them after 15 seconds to prevent blocking.
        """
        current_time = datetime.now()

        session = self.db.get_session()
        try:
            from core.database import Task

            for agent_id, (process, task_id, start_time, log_handle) in list(self.spawner.running_agents.items()):
                # Only check processes that have been running for at least 15 seconds
                elapsed = (current_time - start_time).total_seconds()
                if elapsed < 15:
                    continue

                # Get task from database
                task = session.query(Task).filter_by(id=task_id).first()
                if not task:
                    continue

                # Check if agent released baton (assignee is NULL) but process still running
                if task.assignee is None and process.poll() is None:
                    # Agent updated database but taking too long to exit
                    logger.warning(
                        f"Force-terminating slow-exit process {agent_id} (PID: {process.pid}) "
                        f"for task {task_id} - released baton {elapsed:.1f}s ago but still running"
                    )

                    # Force kill the process
                    try:
                        process.terminate()
                        process.wait(timeout=3)
                    except:
                        process.kill()
                        process.wait()

                    # Clean up
                    if log_handle and not log_handle.closed:
                        log_handle.close()

                    self.spawner._unregister_agent_from_db(agent_id)
                    del self.spawner.running_agents[agent_id]

                    logger.info(f"Slow-exit process {agent_id} terminated - freeing concurrency slot")

        except Exception as e:
            logger.error(f"Error terminating slow-exit processes: {e}", exc_info=True)
        finally:
            session.close()

    def _check_dependencies_complete(self, task: Task, session) -> bool:
        """
        Check if all dependencies for a task are completed.

        Args:
            task: Task to check
            session: Database session

        Returns:
            True if all dependencies are done, False otherwise
        """
        deps = task.get_dependencies()
        if not deps:
            return True  # No dependencies

        for dep_id in deps:
            dep_task = session.query(Task).filter_by(id=dep_id).first()
            if not dep_task:
                logger.warning(f"Task {task.id} has non-existent dependency: {dep_id}")
                return False
            if dep_task.status != "done":
                logger.debug(f"Task {task.id} waiting for dependency {dep_id} (status: {dep_task.status})")
                return False

        return True

    async def _process_qa_gate(self):
        """
        Process QA gate for ready_for_qa tasks.

        Spawns QA agents to test completed developer tasks.
        Only processes tasks whose dependencies are all complete.
        """
        # Get tasks ready for QA (status = ready_for_qa)
        # Order by updated_at (first to reach ready_for_qa gets priority)
        # CRITICAL: Only get tasks with NULL assignee (no agent holds the baton)
        session = self.db.get_session()
        try:
            tasks = session.query(Task).filter(
                Task.status == "ready_for_qa",
                Task.assignee.is_(None)  # Only tasks without an active agent (baton holder)
            ).order_by(Task.updated_at.asc()).all()

            if not tasks:
                return

            logger.info(f"Found {len(tasks)} tasks ready for QA (Priority 1 queue)")

            for task in tasks:
                # Check dependencies first
                if not self._check_dependencies_complete(task, session):
                    logger.info(f"Skipping QA for task {task.id}: dependencies not complete")
                    continue

                # Check if we can spawn a QA agent
                qa_count = self.spawner.get_agent_count_by_role("qa")
                if qa_count >= 5:
                    logger.debug("QA agent limit reached, will process on next iteration")
                    break

                # RACE CONDITION PREVENTION: Spawn agent FIRST, then claim atomically
                # Step 1: Get available agent
                available_agent_id = self.spawner._get_available_agent("qa")
                if not available_agent_id:
                    logger.debug("No available QA agents, will try on next iteration")
                    continue

                # Step 2: Get agent name for prompt
                from core.config import get_agent_name
                agent_name = get_agent_name(available_agent_id)

                # Step 3: Generate prompt with agent info
                prompt = self._generate_qa_prompt(task, available_agent_id, agent_name)

                # Step 4: SPAWN THE AGENT FIRST (adds to running_agents immediately)
                success, agent_id = self.spawner.spawn_agent(
                    role="qa",
                    task_id=task.id,
                    prompt=prompt
                )

                if not success:
                    logger.warning(f"Failed to spawn QA agent for task {task.id}")
                    continue

                logger.info(f"QA agent {agent_id} spawned for task {task.id}, now claiming task atomically")

                # Step 4: NOW atomically claim the task (agent already in running_agents)
                result = session.execute(
                    sql_update(Task)
                    .where(Task.id == task.id, Task.assignee.is_(None))
                    .values(assignee=agent_id, status="in_qa")
                )
                session.commit()

                if result.rowcount == 0:
                    # Race condition - another orchestrator claimed it first
                    logger.warning(
                        f"Task {task.id} was already claimed by another orchestrator, "
                        f"killing spawned QA agent {agent_id}"
                    )
                    # Kill the orphaned agent
                    self.spawner.terminate_agent(agent_id)
                    continue

                # Success - task claimed, agent running
                logger.info(f"Task {task.id} successfully claimed by QA agent {agent_id}")

                # Log start
                self.db.log_action(
                    task_id=task.id,
                    agent_id=agent_id,
                    action="qa_started",
                    notes="QA review started - baton passed to QA agent"
                )

        finally:
            session.close()

    async def _process_security_gate(self):
        """
        Process Security gate for ready_for_security tasks.

        Spawns Security agents to scan tasks that passed QA.
        Only processes tasks whose dependencies are all complete.
        """
        # Get tasks ready for Security (status = ready_for_security)
        # Order by updated_at (first to reach ready_for_security gets priority)
        session = self.db.get_session()
        try:
            tasks = session.query(Task).filter(
                Task.status == "ready_for_security",
                Task.assignee.is_(None)  # Only tasks without an active agent (baton holder)
            ).order_by(Task.updated_at.asc()).all()

            if not tasks:
                return

            logger.info(f"Found {len(tasks)} tasks ready for Security review (Priority 1 queue)")

            for task in tasks:
                # Check dependencies first
                if not self._check_dependencies_complete(task, session):
                    logger.info(f"Skipping Security for task {task.id}: dependencies not complete")
                    continue

                # Check if we can spawn a Security agent
                sec_count = self.spawner.get_agent_count_by_role("security")
                if sec_count >= 5:
                    logger.debug("Security agent limit reached, will process on next iteration")
                    break

                # RACE CONDITION PREVENTION: Spawn agent FIRST, then claim atomically
                # Step 1: Get available agent
                available_agent_id = self.spawner._get_available_agent("security")
                if not available_agent_id:
                    logger.debug("No available Security agents, will try on next iteration")
                    continue

                # Step 2: Get agent name for prompt
                from core.config import get_agent_name
                agent_name = get_agent_name(available_agent_id)

                # Step 3: Generate prompt with agent info
                prompt = self._generate_security_prompt(task, available_agent_id, agent_name)

                # Step 4: SPAWN THE AGENT FIRST (adds to running_agents immediately)
                success, agent_id = self.spawner.spawn_agent(
                    role="security",
                    task_id=task.id,
                    prompt=prompt
                )

                if not success:
                    logger.warning(f"Failed to spawn Security agent for task {task.id}")
                    continue

                logger.info(f"Security agent {agent_id} spawned for task {task.id}, now claiming task atomically")

                # Step 4: NOW atomically claim the task (agent already in running_agents)
                result = session.execute(
                    sql_update(Task)
                    .where(Task.id == task.id, Task.assignee.is_(None))
                    .values(assignee=agent_id, status="in_security")
                )
                session.commit()

                if result.rowcount == 0:
                    # Race condition - another orchestrator claimed it first
                    logger.warning(
                        f"Task {task.id} was already claimed by another orchestrator, "
                        f"killing spawned Security agent {agent_id}"
                    )
                    # Kill the orphaned agent
                    self.spawner.terminate_agent(agent_id)
                    continue

                # Success - task claimed, agent running
                logger.info(f"Task {task.id} successfully claimed by Security agent {agent_id}")

                # Log start
                self.db.log_action(
                    task_id=task.id,
                    agent_id=agent_id,
                    action="security_started",
                    notes="Security scan started - baton passed to Security agent"
                )

        finally:
            session.close()

    def _get_ready_tasks(self) -> List[Task]:
        """
        Get tasks ready for execution.

        A task is ready if:
        - status in ["todo", "qa_failed", "security_failed"]
        - assignee is None
        - all dependencies are completed (status = "done")

        Returns:
            List of ready tasks
        """
        session = self.db.get_session()
        try:
            # Get all tasks needing development work (todo, qa_failed, security_failed)
            tasks = session.query(Task).filter(
                Task.status.in_(["todo", "qa_failed", "security_failed"]),
                Task.assignee.is_(None)
            ).order_by(Task.priority.desc()).all()

            ready = []

            for task in tasks:
                # Check dependencies using centralized method
                if self._check_dependencies_complete(task, session):
                    ready.append(task)

            return ready

        finally:
            session.close()

    async def _spawn_agents_for_tasks(self, tasks: List[Task]):
        """
        Spawn developer agents for ready tasks.
        Frontend developers reference docs/ui_standards.md for design guidance.

        Args:
            tasks: List of ready tasks
        """
        session = self.db.get_session()
        try:
            for task in tasks:
                # Double-check dependencies before spawning (safety check)
                if not self._check_dependencies_complete(task, session):
                    logger.warning(f"Task {task.id} dependencies not complete, skipping spawn")
                    continue

                # Check concurrency limits
                if len(self.spawner.running_agents) >= self.max_concurrency:
                    logger.debug("Max concurrency reached, will spawn more agents on next iteration")
                    break

                # Determine actual developer role to spawn
                # For failed tasks, use agent_type to determine which developer to assign
                if task.status in ["qa_failed", "security_failed"]:
                    # Use agent_type field to route back to correct developer type
                    role = f"{task.agent_type}_developer" if task.agent_type else task.role
                else:
                    # New task - use role field directly
                    role = task.role

                # Validate role
                valid_roles = ["frontend_developer", "backend_developer", "database_developer", "ui_designer", "devops_developer"]
                if role not in valid_roles:
                    logger.warning(f"Task {task.id} has invalid role: {role}. Defaulting to backend_developer")
                    role = "backend_developer"

                # RACE CONDITION PREVENTION: Spawn agent FIRST, then claim atomically
                # Step 1: Get an available agent for this role
                available_agent_id = self.spawner._get_available_agent(role)
                if not available_agent_id:
                    logger.debug(f"No available agents for role {role}, will try on next iteration")
                    continue

                # Step 2: Get agent name for prompt
                from core.config import get_agent_name
                agent_name = get_agent_name(available_agent_id)

                # Step 3: Generate prompt with agent info
                if role == "database_developer":
                    prompt = self._generate_database_prompt(task, available_agent_id, agent_name)
                elif role == "ui_designer":
                    prompt = self._generate_ui_designer_prompt(task, available_agent_id, agent_name)
                elif role == "devops_developer":
                    prompt = self._generate_devops_prompt(task, available_agent_id, agent_name)
                else:
                    prompt = self._generate_developer_prompt(task, role, available_agent_id, agent_name)

                # Step 4: SPAWN THE AGENT FIRST (adds to running_agents immediately)
                success, agent_id = self.spawner.spawn_agent(
                    role=role,
                    task_id=task.id,
                    prompt=prompt
                )

                if not success:
                    logger.warning(f"Failed to spawn agent for task {task.id}")
                    continue

                logger.info(f"Agent {agent_id} spawned for task {task.id}, now claiming task atomically")

                # Step 4: Determine new status based on current task status
                if task.status == "qa_failed":
                    new_status = "qa_fixing"
                elif task.status == "security_failed":
                    new_status = "security_fixing"
                else:  # todo or other states
                    new_status = "in_development"

                # Step 5: NOW atomically claim the task (agent already in running_agents)
                result = session.execute(
                    sql_update(Task)
                    .where(Task.id == task.id, Task.assignee.is_(None))
                    .values(assignee=agent_id, status=new_status)
                )
                session.commit()

                if result.rowcount == 0:
                    # Race condition - another orchestrator claimed it first
                    logger.warning(
                        f"Task {task.id} was already claimed by another orchestrator, "
                        f"killing spawned agent {agent_id}"
                    )
                    # Kill the orphaned agent
                    self.spawner.terminate_agent(agent_id)
                    continue

                # Success - task claimed, agent running
                logger.info(f"Task {task.id} successfully claimed by agent {agent_id} (status: {new_status})")

                # Log start with appropriate message
                if new_status == "qa_fixing":
                    notes = "Fixing QA issues"
                elif new_status == "security_fixing":
                    notes = "Fixing security vulnerabilities"
                else:
                    notes = "Development started"

                self.db.log_action(
                    task_id=task.id,
                    agent_id=agent_id,
                    action="started",
                    notes=notes
                )

        finally:
            session.close()

    def _generate_developer_prompt(self, task: Task, role: str, agent_id: str, agent_name: str) -> str:
        """
        Generate prompt for developer agent with task history awareness.

        Agent reads context from tasks.db and task_logs to understand previous work.

        Args:
            task: Task to generate prompt for
            role: Developer role (frontend_developer or backend_developer)
            agent_id: Agent ID (e.g., "frontend_developer_1")
            agent_name: Human-readable agent name (e.g., "Maya")

        Returns:
            Prompt string
        """
        # Extract relevant context from planning docs
        from core.context_extractor import extract_relevant_context
        relevant_context = extract_relevant_context(
            self.project_dir,
            task.description or "",
            role
        )

        return f"""# Task Assignment: {task.id}

You are **{agent_name}** (Agent ID: `{agent_id}`) working on task **{task.id}** as a **{role}**.

## Instructions

1. **Read your task details from the database**:
   - Connect to `.relay/tasks.db`
   - Query: SELECT * FROM tasks WHERE id = "{task.id}"
   - The `description` field contains the main task requirements
   - Note the task `status`:
     * "in_development" = New feature implementation
     * "qa_fixing" = Fixing issues found by QA
     * "security_fixing" = Fixing vulnerabilities found by Security
   - Read the status to understand what kind of work you're doing

2. **CRITICAL: Review/Create task history markdown log**:
   - Check if `.relay/logs/{task.id}.md` exists

   **If the file does NOT exist (FIRST RUN - you're the first developer):**
   - Create the file with this header structure:
     ```markdown
     # Task {task.id}: [task title from database]

     ## 📋 Task Description

     [task description from database]

     ---

     ## 📝 Task Log

     ### 🔨 Development Started
     **Time:** [current timestamp YYYY-MM-DD HH:MM:SS]
     **Agent:** {agent_name} ({agent_id})
     **Status:** Development in progress

     ```

   **If the file EXISTS (REWORK/FIX - work was done before):**
   - READ IT CAREFULLY to understand the FULL story
   - Look for:
     * What features were already implemented
     * What QA tested and found issues with
     * What security vulnerabilities were reported
     * What fixes were attempted and their results
   - **DO NOT repeat the same mistakes!**
   - Build upon previous work, don't start from scratch

3. **Also check task_logs table for structured data**:
   - Query: SELECT * FROM task_logs WHERE task_id = "{task.id}" ORDER BY created_at ASC
   - This provides timestamps and structured status info

4. **Read relevant planning context**:

   The following sections from planning documents are relevant to your task:

{relevant_context}

   **Note:** If you need additional context not provided above, you can read the full files:
   - `docs/system_design.md`
   - `docs/security_policy.md`
   - `docs/ui_standards.md`
   - `docs/master_plan.md`

5. **Complete the task**:
   - If status was "todo": Implement the feature from scratch
   - If status was "qa_failed": Fix the QA issues documented in task_logs
   - Focus on fixing issues reported in previous QA/Security reviews if this is a rework

5b. **CRITICAL - Verify Build Configuration & Dependencies**:
   - Before marking ANY task complete, verify:
     * All referenced packages in config files (vite.config, postcss.config, etc.) are installed
     * Run the build command (npm run build) to catch configuration errors
   - **Common issues to check:**
     * Tailwind CSS v4 requires @tailwindcss/postcss package
     * PostCSS plugins must be installed as dependencies
     * Vite plugins must be in package.json

6. **For frontend tasks - CONDITIONAL VISUAL VERIFICATION**:

   **Step 1: Determine task type:**
   - **UI/Styling tasks**: Building components, pages, forms, buttons, layouts, styling existing components, visual changes
   - **Logic tasks**: API integration, state management, utilities, hooks, services, data fetching
   - **Config tasks**: Routing setup, build configuration, environment setup, tooling

   **Step 2: Apply appropriate verification:**

   **For UI/STYLING tasks - MANDATORY VISUAL VERIFICATION:**
   - **BEFORE marking complete, you MUST verify styling is working:**
     a. Run `npm run dev` and visit the page in browser
     b. Take screenshots of the rendered page and save it in `.relay/logs/{task.id}_screenshots/` for QA reference
     c. **CRITICAL CHECK**: Verify page is NOT unstyled
        - If content looks like plain black text on white background = FAILURE
        - If buttons are browser-default styled = FAILURE
        - If there's no spacing/layout/colors = FAILURE
     d. Check browser console for:
        - Failed CSS requests
        - PostCSS/Tailwind errors
        - Missing module errors
     e. Verify against design system in docs/ui_standards.md (if exists)
   - **If styling is broken or missing:**
     * Check package.json has all CSS framework dependencies
     * Check config files (postcss.config.js, tailwind.config.js) match installed packages
     * Run build command and fix any errors
     * DO NOT mark as ready_for_qa until styling works!

   **For Logic/Config tasks - BASIC VERIFICATION:**
   - Run `npm run dev` to ensure app still starts
   - Check browser console for errors related to your changes
   - Test the specific functionality you implemented
   - Visual styling verification is NOT required (unless you touched UI code)

7. **CRITICAL: Document your work in the markdown log**:
   - Append to `.relay/logs/{task.id}.md` with a DETAILED summary:
     ```
     ### ✅ Development Completed
     **Time:** [current timestamp in format YYYY-MM-DD HH:MM:SS]
     **Agent:** {agent_name} ({agent_id})
     **Status:** Ready for QA

     **Work Summary:**
     - [What you implemented/fixed - be SPECIFIC]
     - [Key decisions made]
     - [Files created/modified]
     - [Any important notes for QA/future developers]

     **Files Modified:**
     - `path/to/file1.js`
     - `path/to/file2.py`

     ---
     ```
   - **Be DETAILED and SPECIFIC** - this helps QA know what to test and future developers understand what was done
   - If fixing QA/security issues, explain exactly what you fixed and how
   - Use your agent name "{agent_name}" and ID "{agent_id}" in the log entry

8. **Report completion and RELEASE THE BATON**:
   - Update task: UPDATE tasks SET status='ready_for_qa', assignee=NULL WHERE id='{task.id}'

9. **EXIT**: After updating the status and releasing the baton, your work is complete. Exit immediately.

**CRITICAL - FORCE IMMEDIATE EXIT:**
After updating the database, you MUST run this Python code to immediately terminate:
```python
import sys
sys.exit(0)
```

Without sys.exit(0), the process takes 30s-2min to shutdown, blocking other agents!

**CRITICAL - BATON MECHANISM**:
- You hold the "baton" (task ownership) via the assignee field
- MUST set assignee=NULL when updating status to release the baton
- Reference the Security Policy (docs/security_policy.md) while implementing!

**CRITICAL - TASK HISTORY**:
- ALWAYS read `.relay/logs/{task.id}.md` (if it exists) to understand the full history of work on this task
- If this is a qa_failed or security_failed task, focus on fixing reported issues
- Do NOT repeat the same implementation that failed before
- Build upon previous work instead of starting fresh
- Every work you do should be informed by the history of what was done and what failed before
- Log every decision and milestone in `.relay/logs/{task.id}.md` so future agents understand the history

**SINGLE source of truth**:
- tasks table: Main task data and current status
- `.relay/logs/{task.id}.md`: Complete history of all work done on this task
- Once you update the status to ready_for_qa, EXIT - do not wait for further instructions
"""

    def _generate_qa_prompt(self, task: Task, agent_id: str, agent_name: str) -> str:
        """
        Generate prompt for QA agent with task history awareness.

        Args:
            task: Task to generate QA prompt for
            agent_id: Agent ID (e.g., "qa_1")
            agent_name: Human-readable agent name (e.g., "Sarah")

        Returns:
            QA prompt string
        """
        # Extract relevant context from planning docs
        from core.context_extractor import extract_relevant_context
        relevant_context = extract_relevant_context(
            self.project_dir,
            task.description or "",
            task.role or "qa"
        )

        return f"""# QA Review: {task.id}

You are **{agent_name}** (Agent ID: `{agent_id}`) reviewing task **{task.id}** as a QA agent.

**NOTE**: This task has been assigned to you by the orchestrator. You have exclusive ownership.

## Instructions

1. **Read the complete task history from markdown log**:
   - Read `.relay/logs/{task.id}.md` to understand what has been done
   - **If file doesn't exist:** Create it with task header (get title/description from database), then add a note that QA started
   - **This file should contain the FULL context:**
     * Original task requirements
     * What the developer implemented
     * If this task failed QA before and what issues were found
     * What fixes the developer made
   - **Use this to focus your testing** - prioritize areas that failed before

2. **Also check database for task details**:
   - Connect to `.relay/tasks.db`
   - Query: SELECT * FROM tasks WHERE id = "{task.id}"
   
2b. **CRITICAL - Pre-Check: Build Validation**:
   - **BEFORE starting functional tests**, verify the build works:
     * Run `npm run build` (or equivalent) to check for config errors
     * Check terminal output for missing dependencies or plugin errors
     * If build fails = AUTOMATIC QA FAIL

3. **Review implementation - ENHANCED**:
   - Check code quality and correctness
   - Test functionality against requirements
   - Verify error handling
   - Check edge cases
   - **For frontend tasks:**
     * **FIRST**: Determine task type (see step 4)
     * Apply appropriate verification based on task type
     * Test functionality against requirements

4. **CRITICAL - Conditional Frontend Verification**:

   **Step 4a - Determine Task Type:**
   Read the task description and developer's work log to classify:
   - **UI/Styling task**: Building/modifying components, pages, forms, buttons, layouts, CSS changes, visual features
   - **Logic task**: API integration, state management, utilities, hooks, services, data processing
   - **Config task**: Routing, build config, environment setup, tooling

   **Step 4b - For UI/STYLING Tasks - MANDATORY VISUAL VERIFICATION:**
   - Launch the application (npm run dev or preview build)
   - Navigate to the implemented/modified pages
   - Take screenshots
   - **CRITICAL FAILURE CONDITIONS - Any of these = IMMEDIATE QA FAIL:**
     * ❌ Page is completely unstyled (plain text, no colors/spacing)
     * ❌ Buttons look like browser defaults (no custom styling)
     * ❌ No layout/grid system visible
     * ❌ Browser console shows CSS loading errors
     * ❌ Browser console shows "Failed to load module" for CSS files
     * ❌ Browser console shows PostCSS/Tailwind errors
   - **If ANY styling failure found:**
     * STOP testing immediately
     * Document: "CRITICAL: Styling not loading - likely missing dependency"
     * Check package.json vs config files for missing packages
     * Mark as QA FAILED with detailed description
   - **If styling check passes, proceed with functional tests:**
     * Use BrowserTestRunner to verify UI
     * Test user interactions
     * Check for JavaScript console errors
     * Verify responsive design
     * Validate against design system colors/fonts/spacing/components

   **Step 4c - For Logic/Config Tasks - FUNCTIONAL VERIFICATION:**
   - Run `npm run dev` to ensure app still works
   - Test the specific functionality implemented
   - Check browser console for errors related to the changes
   - Verify the logic/configuration works as expected
   - Visual styling verification is NOT required (unless UI code was modified)

5. **Browser Console Monitoring**:
   - Open browser DevTools Console tab
   - Look for ERROR messages (not just warnings)
   - **Auto-fail conditions:**
     * Failed to load CSS/stylesheet
     * Module not found errors
     * PostCSS/Tailwind compilation errors
     * 404s for asset files

6. **CRITICAL: Document your QA results in the markdown log**:
   - Append to `.relay/logs/{task.id}.md` with DETAILED test results:
     ```
     ### ✅ QA Testing PASSED  (or ❌ QA Testing FAILED)
     **Time:** [current timestamp in format YYYY-MM-DD HH:MM:SS]
     **Agent:** {agent_name} ({agent_id})
     **Status:** [Ready for Security / Needs Developer Fixes]

     **Test Summary:**
     - [What you tested]
     - [Test results]
     - [Any edge cases checked]

     **Issues Found:** (if failed)
     1. [Specific issue with reproduction steps]
     2. [Another issue with expected vs actual behavior]

     ---
     ```
   - **Be SPECIFIC about failures** - developers need exact reproduction steps and clear descriptions
   - Use your agent name "{agent_name}" and ID "{agent_id}" in the log entry

7. **Report results and RELEASE THE BATON**:
   - If all tests pass:
     - UPDATE tasks SET status='ready_for_security', assignee=NULL WHERE id='{task.id}'
   - If tests fail:
     - UPDATE tasks SET status='qa_failed', assignee=NULL WHERE id='{task.id}'

8. **EXIT**: After updating the status and releasing the baton, your QA work is complete. Exit immediately.

**CRITICAL - FORCE IMMEDIATE EXIT:**
After updating the database, you MUST run this Python code to immediately terminate:
```python
import sys
sys.exit(0)
```

Without sys.exit(0), the process takes 30s-2min to shutdown, blocking other agents!

**CRITICAL - BATON MECHANISM**:
- You hold the "baton" (task ownership) while working on this task
- MUST set assignee=NULL when updating status to release the baton
- Database is the SINGLE source of truth of task status
- `.relay/logs/{task.id}.md` is the SINGLE source of truth for task history and context for future agents

**CRITICAL - TASK HISTORY**:
- ALWAYS read `.relay/logs/{task.id}.md` to see previous QA results
- If this task was qa_failed before, verify the fixes
- Document your findings clearly in `.relay/logs/{task.id}.md` so the developer knows what to fix
- Be specific: "Button X doesn't work when Y" not just "UI broken"

**Once you update the status, EXIT - do not wait for further instructions**

---

## Visual QA Checklist for Frontend Tasks

**NOTE**: This checklist is for UI/STYLING tasks only. For logic/config tasks, skip visual checks and focus on functional testing.

### Task Type Classification:
- **UI/Styling**: Use full checklist below
- **Logic/Config**: Skip visual checks, only verify functionality

### ✅ PASS Criteria (UI/Styling Tasks):
- [ ] Page loads without console errors
- [ ] CSS/styling is fully applied
- [ ] Colors match design system (if defined)
- [ ] Spacing/padding is present (not browser defaults)
- [ ] Buttons have custom styling
- [ ] Layout/grid system is visible
- [ ] Responsive design works (if applicable)
- [ ] All functionality works as expected

### ❌ FAIL Criteria for UI/Styling Tasks (Any one = QA FAIL):
- [ ] Page is unstyled (plain HTML appearance)
- [ ] Console shows CSS loading errors
- [ ] Console shows "Module not found" for styling dependencies
- [ ] Console shows PostCSS/Tailwind errors
- [ ] Build command fails
- [ ] Missing dependencies referenced in config files
- [ ] Buttons/components use only browser default styling
- [ ] No spacing/colors/layout applied

### ✅ PASS Criteria (Logic/Config Tasks):
- [ ] App runs without errors
- [ ] Implemented functionality works as expected
- [ ] No console errors related to the changes
- [ ] Code quality is acceptable

### 🔍 How to Check:
**For UI/Styling Tasks:**
1. Run `npm run build` - must succeed without errors
2. Run `npm run dev` - must start without errors
3. Open browser DevTools → Console tab
4. Navigate to implemented page
5. Take screenshot
6. Compare screenshot to UI/Styling checklist above

**For Logic/Config Tasks:**
1. Run `npm run dev` - must start without errors
2. Test the specific functionality
3. Check console for errors related to changes
4. Verify requirements are met
"""

    def _generate_security_prompt(self, task: Task, agent_id: str, agent_name: str) -> str:
        """
        Generate prompt for Security agent with task history awareness.

        Args:
            task: Task to generate Security prompt for
            agent_id: Agent ID (e.g., "security_1")
            agent_name: Human-readable agent name (e.g., "Alex")

        Returns:
            Security prompt string
        """
        # Extract relevant context from security policy
        from core.context_extractor import extract_relevant_context
        relevant_context = extract_relevant_context(
            self.project_dir,
            task.description or "",
            "security"
        )

        return f"""# Security Review: {task.id}

You are **{agent_name}** (Agent ID: `{agent_id}`) performing a security scan on task **{task.id}**.

**NOTE**: This task has been assigned to you by the orchestrator. You have exclusive ownership.

## Instructions

1. **Read the complete task history from markdown log**:
   - Read `.relay/logs/{task.id}.md` to understand what has been done
   - **If file doesn't exist:** Create it with task header (get title/description from database), then add a note that Security scan started
   - **This file should contain the FULL context:**
     * Original task requirements
     * What the developer implemented
     * What QA tested and approved
     * If this task failed security before and what vulnerabilities were found
     * What fixes the developer made
   - **Use this to focus your scan** - prioritize areas that failed before

2. **Also check database for task details**:
   - Connect to `.relay/tasks.db`
   - Query: SELECT * FROM tasks WHERE id = "{task.id}"

3. **Review relevant security policy sections**:

{relevant_context}

   **Note:** If you need additional security policy context, read the full file:
   - `docs/security_policy.md`

4. **Perform security scan**:
   - Check for OWASP Top 10 vulnerabilities
   - Verify input validation
   - Check authentication/authorization
   - Review data encryption
   - Check for insecure dependencies (refer to Forbidden Library list)
   - Scan for hardcoded secrets, API keys, passwords
   - Verify secure configurations

5. **CRITICAL: Document your security scan results in the markdown log**:
   - Append to `.relay/logs/{task.id}.md` with DETAILED scan results:
     ```
     ### ✅ Security Scan PASSED  (or 🚨 Security Scan FAILED)
     **Time:** [current timestamp in format YYYY-MM-DD HH:MM:SS]
     **Agent:** {agent_name} ({agent_id})
     **Status:** [✅ TASK COMPLETE / Needs Developer Fixes]

     **Scan Summary:**
     - [What you scanned for]
     - [Scan results]
     - [Security checks performed]

     **Vulnerabilities Found:** (if failed)
     - **HIGH**: [CVE-XXXX] [Package name version X.Y] - [Description]
     - **MEDIUM**: [Description with specific details]

     ---
     ```
   - **Be SPECIFIC about vulnerabilities** - include CVE numbers, package names/versions, exact issues
   - Use your agent name "{agent_name}" and ID "{agent_id}" in the log entry

6. **Report results and RELEASE THE BATON**:
   - If security scan passes:
     - UPDATE tasks SET status='done', assignee=NULL WHERE id='{task.id}'
   - If security issues found:
     - UPDATE tasks SET status='security_failed', assignee=NULL WHERE id='{task.id}'
     - Update `.relay/logs/{task.id}.md` with detailed vulnerability information so the developer knows exactly what to fix
     - **Be SPECIFIC**: List CVE numbers, vulnerable packages/versions, exact security issues found

7. **EXIT**: After updating the status and releasing the baton, your security review is complete. Exit immediately.

**CRITICAL - FORCE IMMEDIATE EXIT:**
After updating the database, you MUST run this Python code to immediately terminate:
```python
import sys
sys.exit(0)
```

Without sys.exit(0), the process takes 30s-2min to shutdown, blocking other agents!

**CRITICAL - BATON MECHANISM**:
- You hold the "baton" (task ownership) while working on this task
- MUST set assignee=NULL when updating status to release the baton
- Reference docs/security_policy.md for all security requirements!
- Database is the SINGLE source of truth of task status
- `.relay/logs/{task.id}.md` is the SINGLE source of truth for task history and context for future agents


**CRITICAL - TASK HISTORY**:
- ALWAYS read `.relay/logs/{task.id}.md` to see previous security results
- If this task was security_failed before, verify the fixes
- Document your findings clearly with CVE numbers, package names, versions
- Be specific: "Package X version Y has CVE-2024-1234" not just "dependencies vulnerable"

**Once you update the status, EXIT - do not wait for further instructions**
"""


    def _generate_ui_designer_prompt(self, task: Task, agent_id: str, agent_name: str) -> str:
        """
        Generate prompt for UI Designer agent.

        Args:
            task: Task to generate prompt for
            agent_id: Agent ID (e.g., "ui_designer_1")
            agent_name: Human-readable agent name (e.g., "Pixel")

        Returns:
            UI Designer prompt string
        """
        # Extract relevant context from UI standards
        from core.context_extractor import extract_relevant_context
        relevant_context = extract_relevant_context(
            self.project_dir,
            task.description or "",
            "ui_designer"
        )

        return f"""# UI Design Task: {task.id}

You are **{agent_name}** (Agent ID: `{agent_id}`) working on UI design task **{task.id}**.

## Instructions

1. **Read task details from database**:
   - Connect to `.relay/tasks.db`
   - Query: SELECT * FROM tasks WHERE id = "{task.id}"
   - The description field contains design requirements

2. **Review relevant UI standards**:

{relevant_context}

   **Note:** Read full `docs/ui_standards.md` and `docs/system_design.md` for complete context.

3. **Create UI design deliverables**:

   Your output depends on the task:

   **For Wireframes:**
   - Create ASCII/Markdown wireframes in `docs/wireframes/`
   - Show layout, component placement, navigation flow
   - Include annotations for interactions

   **For Component Specifications:**
   - Document in `docs/components/[component-name].md`
   - Include: props, variants, states, accessibility requirements
   - Reference design system (colors, typography, spacing)

   **For Design System Creation:**
   - Define in `docs/ui_standards.md` (if not exists, create it)
   - Include: color palette, typography scale, spacing system
   - Component library choices and naming conventions
   - Accessibility guidelines

4. **Ensure consistency**:
   - Follow existing UI standards (if they exist)
   - Use standard design patterns
   - Consider mobile/responsive requirements
   - Follow accessibility best practices (WCAG 2.1 AA)

5. **Document your work**:
   - Create/update `.relay/logs/{task.id}.md`:
     ```markdown
     ### ✅ Design Complete
     **Time:** [current timestamp YYYY-MM-DD HH:MM:SS]
     **Agent:** {agent_name} ({agent_id})
     **Status:** Ready for QA

     **Design Deliverables:**
     - [List files created]
     - [Key design decisions made]

     **Design Notes:**
     - [Important considerations for implementation]
     - [Component dependencies]
     - [Accessibility requirements]

     **Files Created:**
     - `docs/wireframes/[filename].md`
     - `docs/components/[component].md`
     ```

6. **Update task status**:
   - If design completed successfully:
     * UPDATE tasks SET status='ready_for_qa', assignee=NULL WHERE id='{task.id}'
   - If unable to complete:
     * UPDATE tasks SET status='failed', assignee=NULL WHERE id='{task.id}'
     * Document why in the task log

7. **EXIT immediately** after updating status:
```python
import sys
sys.exit(0)
```

**Design Checklist:**
- [ ] Follows existing UI standards
- [ ] Responsive/mobile-friendly
- [ ] Accessible (WCAG 2.1 AA)
- [ ] Consistent with design system
- [ ] Clear component specifications
- [ ] Implementation-ready

**SINGLE source of truth:**
- tasks table: Task data and status
- `.relay/logs/{task.id}.md`: Design history
- Design files in `docs/wireframes/` and `docs/components/`
"""

    def _generate_devops_prompt(self, task: Task, agent_id: str, agent_name: str) -> str:
        """
        Generate prompt for DevOps agent.

        Args:
            task: Task to generate prompt for
            agent_id: Agent ID (e.g., "devops_1")
            agent_name: Human-readable agent name (e.g., "Docker")

        Returns:
            DevOps prompt string
        """
        # Extract relevant context from system design
        from core.context_extractor import extract_relevant_context
        relevant_context = extract_relevant_context(
            self.project_dir,
            task.description or "",
            "devops"
        )

        return f"""# DevOps Task: {task.id}

You are **{agent_name}** (Agent ID: `{agent_id}`) working on DevOps task **{task.id}**.

## Instructions

1. **Read task details from database**:
   - Connect to `.relay/tasks.db`
   - Query: SELECT * FROM tasks WHERE id = "{task.id}"
   - The description field contains infrastructure/deployment requirements

2. **Review relevant system design sections**:

{relevant_context}

   **Note:** Read full `docs/system_design.md` for complete tech stack and architecture context.

3. **Complete the DevOps task**:

   Your work depends on the task type:

   **For Dockerfile creation:**
   - Review project structure and dependencies
   - Create optimized multi-stage Dockerfile
   - Use appropriate base images (alpine/slim variants)
   - Implement security best practices (non-root user, minimal layers)
   - Create .dockerignore
   - Create docker-compose.yml for local development
   - Test build and run locally

   **For CI/CD setup:**
   - Choose appropriate platform (GitHub Actions recommended)
   - Create workflow files (.github/workflows/)
   - Implement: lint → test → build → (optional) deploy
   - Add status badges to README
   - Test pipeline with dummy commit

   **For environment configuration:**
   - Create .env.example with all variables
   - Document each variable in README
   - Setup environment loading in application
   - Validate required variables on startup
   - Never commit secrets

   **For deployment configuration:**
   - Choose deployment platform (Vercel, Netlify, AWS, etc.)
   - Create deployment configuration files
   - Setup environment variables
   - Document deployment process
   - Test deployment to staging

4. **Follow DevOps best practices**:
   - Infrastructure as Code (IaC)
   - Security-first approach
   - Minimal attack surface
   - Clear documentation
   - Repeatable deployments
   - Health checks and monitoring

5. **Document your work**:
   - Create/update `.relay/logs/{task.id}.md`:
     ```markdown
     ### ✅ DevOps Task Complete
     **Time:** [current timestamp YYYY-MM-DD HH:MM:SS]
     **Agent:** {agent_name} ({agent_id})
     **Status:** Ready for QA

     **Work Summary:**
     - [What you created/configured]
     - [Key decisions made]
     - [Files created/modified]

     **Files Created/Modified:**
     - `Dockerfile`
     - `.github/workflows/ci.yml`
     - `.env.example`
     - etc.

     **Testing:**
     - [How you tested the setup]
     - [Results]

     **Deployment Notes:**
     - [Important considerations for production]
     - [Environment variables needed]
     - [Manual steps required]
     ```

6. **Update task status**:
   - If task completed successfully:
     * UPDATE tasks SET status='ready_for_qa', assignee=NULL WHERE id='{task.id}'
   - If unable to complete:
     * UPDATE tasks SET status='failed', assignee=NULL WHERE id='{task.id}'
     * Document why in the task log

7. **EXIT immediately** after updating status:
```python
import sys
sys.exit(0)
```

**DevOps Checklist:**
- [ ] Configuration follows security best practices
- [ ] Documentation complete (README updated)
- [ ] Tested locally
- [ ] No secrets committed
- [ ] Clear deployment instructions
- [ ] Health checks included (if applicable)

**SINGLE source of truth:**
- tasks table: Task data and status
- `.relay/logs/{task.id}.md`: DevOps work history
"""

    def _generate_database_prompt(self, task: Task, agent_id: str, agent_name: str) -> str:
        """
        Generate prompt for Database agent (migration generation).

        Args:
            task: Task to generate prompt for
            agent_id: Agent ID (e.g., "database_1")
            agent_name: Human-readable agent name (e.g., "Schema")

        Returns:
            Database prompt string
        """
        # Extract relevant context from system design
        from core.context_extractor import extract_relevant_context
        relevant_context = extract_relevant_context(
            self.project_dir,
            task.description or "",
            "database"
        )

        return f"""# Database Migration Task: {task.id}

You are **{agent_name}** (Agent ID: `{agent_id}`) creating a database migration for task **{task.id}**.

## Instructions

1. **Read task details from database**:
   - Connect to `.relay/tasks.db`
   - Query: SELECT * FROM tasks WHERE id = "{task.id}"
   - The description field explains what schema changes need migration files

2. **Read parent task work log**:
   - Your task description mentions a parent task (e.g., "for task BE-001")
   - Read `.relay/logs/[parent-task-id].md` to see what was actually implemented
   - Identify all database schema changes made

3. **Review relevant system design sections**:

{relevant_context}

   **Note:** Read full `docs/system_design.md` if you need more database architecture context.

4. **Detect migration framework**:
   - Check project for: Django migrations, Prisma schema, Alembic, or raw SQL
   - Read existing migration files to understand naming/structure conventions
   - Follow the same pattern for your migration

5. **Generate migration file**:
   - **Django**: Create file in `<app>/migrations/XXXX_<description>.py`
   - **Prisma**: Update `schema.prisma`, then run `npx prisma migrate dev --name <description>`
   - **Alembic**: Run `alembic revision -m "<description>"` and edit generated file
   - **Raw SQL**: Create `migrations/<timestamp>_<description>.sql`

6. **Migration must include**:
   - Forward migration (apply changes)
   - Backward migration (rollback changes)
   - All schema changes from parent task:
     * New tables/models
     * Modified columns/fields
     * Indexes
     * Foreign keys
     * Constraints
   - Data transformations if needed (with safety checks)

7. **Test the migration**:
   - Backup test database
   - Run migration forward
   - Verify schema changes applied
   - Run migration backward
   - Verify schema reverted correctly

8. **Document your work**:
   - Create/update `.relay/logs/{task.id}.md` with:
     ```markdown
     ### ✅ Migration Generated
     **Time:** [current timestamp YYYY-MM-DD HH:MM:SS]
     **Agent:** {agent_name} ({agent_id})
     **Status:** Ready for QA

     **Migration Summary:**
     - Migration file: [path to file]
     - Framework: [Django/Prisma/Alembic/SQL]
     - Schema changes:
       * [list all tables/columns/indexes modified]

     **Testing:**
     - Forward migration: [✅ PASS / ❌ FAIL]
     - Backward migration: [✅ PASS / ❌ FAIL]

     **Notes:**
     - [Any important considerations for deploying this migration]
     - [Data loss risks if any]
     ```

9. **Update task status**:
   - If migration created and tested successfully:
     * UPDATE tasks SET status='ready_for_qa', assignee=NULL WHERE id='{task.id}'
   - If unable to create migration:
     * UPDATE tasks SET status='failed', assignee=NULL WHERE id='{task.id}'
     * Document why in the task log

10. **EXIT immediately** after updating status:
```python
import sys
sys.exit(0)
```

**CRITICAL REQUIREMENTS:**
- Migration must be idempotent (safe to run multiple times)
- Migration must be reversible
- No hardcoded IDs or production data
- Test both forward and backward migrations
- Document any data transformation risks

**SINGLE source of truth:**
- tasks table: Task data and status
- `.relay/logs/{task.id}.md`: Migration creation history
- Once status is updated to ready_for_qa, EXIT immediately
"""

    def _all_tasks_complete(self) -> bool:
        """
        Check if all tasks are completed.

        Returns:
            True if all tasks are done, False otherwise
        """
        stats = self.db.get_statistics()
        return stats['total'] > 0 and stats['completed'] == stats['total']

    def _update_dashboard(self):
        """
        Update task status dashboard.

        Generates docs/task_status.md with current progress.
        """
        try:
            dashboard_file = self.project_dir / "docs" / "task_status.md"

            # Get statistics
            stats = self.db.get_statistics()

            # Get tasks by phase
            tasks_by_phase = self.db.get_tasks_grouped_by_phase()

            # Get active agents
            active_agents = self.db.get_active_agents()

            # Generate dashboard
            content = f"""# Task Status Dashboard

**Generated**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Overall Progress

- **Total Tasks**: {stats['total']}
- **Completed**: {stats['completed']}
- **To Do**: {stats['todo']}
- **In Development**: {stats['in_development']}
- **Fixing QA Issues**: {stats['qa_fixing']}
- **Fixing Security Issues**: {stats['security_fixing']}
- **Ready for QA**: {stats['ready_for_qa']}
- **In QA**: {stats['in_qa']}
- **Ready for Security**: {stats['ready_for_security']}
- **In Security**: {stats['in_security']}
- **Failed (QA)**: {stats['qa_failed']}
- **Failed (Security)**: {stats['security_failed']}

**Progress**: {(stats['completed'] / stats['total'] * 100) if stats['total'] > 0 else 0:.1f}%

## Active Agents

"""

            if active_agents:
                session = self.db.get_session()
                try:
                    for agent in active_agents:
                        # Find the task this agent is currently assigned to
                        task = session.query(Task).filter(Task.assignee == agent.agent_id).first()
                        task_id = task.id if task else "-"
                        content += f"- **{agent.agent_name}** ({agent.agent_type}): Working on {task_id}\n"
                finally:
                    session.close()
            else:
                content += "No active agents\n"

            content += "\n## Tasks by Phase\n\n"

            for phase, tasks in tasks_by_phase.items():
                total = len(tasks)
                completed = sum(1 for t in tasks if t.status == 'done')
                content += f"### {phase}\n\n"
                content += f"**Progress**: {completed}/{total} ({(completed/total*100) if total > 0 else 0:.0f}%)\n\n"

                for task in tasks:
                    status_icon = "✅" if task.status == "done" else "🔄" if task.status == "in_progress" else "⏳"
                    content += f"- {status_icon} **{task.id}**: {task.title} ({task.status})\n"

                content += "\n"

            # Write dashboard
            dashboard_file.write_text(content)

        except Exception as e:
            logger.error(f"Failed to update dashboard: {e}", exc_info=True)

    def _update_cli_dashboard(self):
        """
        Update real-time CLI dashboard.

        Gathers current state and updates the dashboard display.
        """
        try:
            # Get statistics from database
            stats = self.db.get_statistics()

            # Recalculate active agent counts based on actual running agents
            # This ensures accuracy even if task statuses are stale
            dev_count = 0
            qa_count = 0
            sec_count = 0

            for agent_id in self.spawner.running_agents.keys():
                if 'frontend' in agent_id or 'backend' in agent_id:
                    dev_count += 1
                elif 'qa' in agent_id:
                    qa_count += 1
                elif 'security' in agent_id:
                    sec_count += 1

            # Override active counts with actual running agents
            # But keep database counts for ready_for_qa/ready_for_security (they're accurate)
            stats['in_development'] = dev_count
            stats['in_qa'] = qa_count
            stats['in_security'] = sec_count
            # Note: stats['ready_for_qa'] and stats['ready_for_security'] come from DB and are accurate

            # Get active agents - iterate through running agents directly
            active_agents_display = []
            session = self.db.get_session()
            try:
                from core.database import Task, Agent

                for agent_id, (process, task_id, start_time, _) in self.spawner.running_agents.items():
                    # Get task details
                    task = session.query(Task).filter_by(id=task_id).first()
                    if not task:
                        continue

                    # Get agent details from agents table
                    agent = session.query(Agent).filter_by(agent_id=agent_id).first()
                    if agent:
                        # Use human-readable name and type from database
                        agent_name = agent.agent_name
                        agent_type_db = agent.agent_type

                        # Map agent_type to display name
                        type_map = {
                            'developer': 'Developer',
                            'frontend_developer': 'Frontend Developer',
                            'backend_developer': 'Backend Developer',
                            'qa': 'QA',
                            'security': 'Security',
                            'ui_agent': 'UI/UX'
                        }
                        agent_type = type_map.get(agent_type_db, agent_type_db.title())
                    else:
                        # Fallback if agent not in database
                        agent_name = agent_id
                        if 'frontend' in agent_id:
                            agent_type = 'Frontend Developer'
                        elif 'backend' in agent_id:
                            agent_type = 'Backend Developer'
                        elif 'qa' in agent_id:
                            agent_type = 'QA'
                        elif 'security' in agent_id:
                            agent_type = 'Security'
                        elif 'ui_agent' in agent_id:
                            agent_type = 'UI/UX'
                        else:
                            agent_type = 'Developer'

                    # Use task status directly (it's the most accurate)
                    status = task.status

                    # Filter: Only show agents working on tasks in active work states
                    # Skip agents on tasks that have moved to waiting states (ready_for_qa, ready_for_security)
                    # or terminal states (done, todo)
                    if status not in ACTIVE_WORK_STATES:
                        logger.debug(
                            f"Skipping agent {agent_id} from dashboard - task {task_id} "
                            f"in non-active state: {status}"
                        )
                        continue

                    active_agents_display.append(AgentDisplay(
                        task_id=task.id,
                        task_title=task.title,
                        agent_name=agent_name,
                        agent_type=agent_type,
                        status=status,
                        start_time=start_time
                    ))

            finally:
                session.close()

            # Get waiting tasks (ready to be picked up)
            waiting_tasks = []
            ready_tasks = self._get_ready_tasks()
            for task in ready_tasks:
                # Determine role
                role = task.role
                if task.status in ["qa_failed", "security_failed"]:
                    role = f"{task.agent_type}_developer" if task.agent_type else task.role

                waiting_tasks.append((task.id, task.title, role))

            # Get recent completions
            recent_completions = []
            session = self.db.get_session()
            try:
                from core.database import Task, TaskLog
                completed_tasks = session.query(Task).filter(
                    Task.status == "done"
                ).order_by(Task.updated_at.desc()).limit(3).all()

                for task in completed_tasks:
                    # Calculate completion time from task logs
                    # Find "started" action and "completed" or "security_passed" action
                    started_log = session.query(TaskLog).filter(
                        TaskLog.task_id == task.id,
                        TaskLog.action == "started"
                    ).order_by(TaskLog.created_at.asc()).first()

                    completed_log = session.query(TaskLog).filter(
                        TaskLog.task_id == task.id,
                        TaskLog.action.in_(["completed", "security_passed"])
                    ).order_by(TaskLog.created_at.desc()).first()

                    if started_log and completed_log:
                        completion_time = (completed_log.created_at - started_log.created_at).total_seconds() / 60
                    else:
                        completion_time = 0

                    recent_completions.append((task.id, task.title, completion_time))

            finally:
                session.close()

            # Calculate elapsed time and average task time
            # Note: The executor doesn't track start_time yet, so we'll use None for now
            # This can be enhanced later by adding a start_time field to the Executor class
            elapsed_time = None  # TODO: Add start_time tracking to Executor
            avg_task_time = None  # TODO: Calculate from task logs

            # Update dashboard
            self.dashboard.update(
                stats=stats,
                active_agents=active_agents_display,
                waiting_tasks=waiting_tasks,
                max_concurrency=self.max_concurrency,
                recent_completions=recent_completions,
                elapsed_time=elapsed_time,
                avg_task_time=avg_task_time
            )

        except Exception as e:
            logger.error(f"Failed to update CLI dashboard: {e}", exc_info=True)

    async def _check_and_create_migration_task(self, completed_task):
        """
        Check if a completed backend task requires a database migration.

        Detects schema changes by looking for keywords in task description
        and work log. If detected, creates a migration task.

        Args:
            completed_task: The completed backend task
        """
        try:
            # Keywords that indicate database schema changes
            schema_keywords = [
                'model', 'schema', 'table', 'column', 'field',
                'database', 'migration', 'index', 'constraint',
                'foreign key', 'relationship', 'entity'
            ]

            # Check task description for schema-related keywords
            desc_lower = (completed_task.description or "").lower()
            has_schema_keywords = any(kw in desc_lower for kw in schema_keywords)

            # Read task log to check what was actually implemented
            log_file = self.project_dir / ".relay" / "logs" / f"{completed_task.id}.md"
            log_mentions_schema = False

            if log_file.exists():
                log_content = log_file.read_text().lower()
                log_mentions_schema = any(kw in log_content for kw in schema_keywords)

            # If no schema changes detected, skip
            if not has_schema_keywords and not log_mentions_schema:
                logger.debug(f"No schema changes detected for task {completed_task.id}")
                return

            # Check if migration task already exists for this task
            migration_id = f"MIG-{completed_task.id}"
            existing = self.db.get_task(migration_id)
            if existing:
                logger.debug(f"Migration task {migration_id} already exists")
                return

            # Create migration task
            migration_task = {
                "id": migration_id,
                "title": f"Create database migration for {completed_task.id}",
                "description": f"""Generate database migration file for schema changes in task {completed_task.id}.

**Parent Task:** {completed_task.title}

**Context:**
Read `.relay/logs/{completed_task.id}.md` to understand what database schema changes were made.

**Requirements:**
1. Review the code changes from task {completed_task.id}
2. Identify all database schema modifications:
   - New tables/models
   - Modified columns/fields
   - New indexes
   - Foreign key constraints
   - Data type changes

3. Generate appropriate migration file:
   - For Django: Create migration in appropriate app's migrations/ folder
   - For Prisma: Update schema.prisma and generate migration
   - For Alembic: Create new migration version
   - For raw SQL: Create timestamped .sql migration file

4. Ensure migration is:
   - Idempotent (can run multiple times safely)
   - Reversible (includes downgrade/rollback)
   - Tested (doesn't break existing data)

5. Reference docs/system_design.md for database architecture

**Acceptance Criteria:**
- Migration file created in correct location
- Migration includes all schema changes from parent task
- Migration is reversible
- Migration tested locally
- No data loss on upgrade/downgrade

References: docs/system_design.md
""",
                "phase": completed_task.phase,
                "role": "database_developer",
                "agent_type": "database",
                "dependencies": [completed_task.id],  # Must complete after parent
                "priority": completed_task.priority,
                "complexity": 2,
                "status": "todo"
            }

            self.db.create_task(migration_task)

            logger.info(f"✅ Created migration task: {migration_id} for {completed_task.id}")

            self.db.log_action(
                task_id=migration_id,
                agent_id="system",
                action="created",
                notes=f"Auto-generated migration task for schema changes in {completed_task.id}"
            )

        except Exception as e:
            logger.error(f"Failed to create migration task for {completed_task.id}: {e}")
            import traceback
            traceback.print_exc()
