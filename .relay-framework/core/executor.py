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
import yaml
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

        # Vault writer queue (single-worker queue to serialize vault writes)
        self.vault_queue = asyncio.Queue(maxsize=10)
        self.vault_worker_task = None

        logger.info(f"Executor initialized: project_dir={project_dir}, max_concurrency={max_concurrency}")

    def shutdown(self):
        """Request shutdown and terminate all agents."""
        logger.info("Shutdown requested")
        self.shutdown_requested = True
        self.spawner.terminate_all()

        # Cancel vault writer worker
        if self.vault_worker_task and not self.vault_worker_task.done():
            self.vault_worker_task.cancel()

    async def _vault_writer_worker(self):
        """
        Background worker that processes vault writes from queue.

        Ensures only one vault write happens at a time (vault writes are 10-30s Claude subprocess calls).
        """
        logger.info("Vault writer worker started")

        while not self.shutdown_requested:
            try:
                # Wait for vault write request (timeout to check shutdown periodically)
                task_id, task_data = await asyncio.wait_for(
                    self.vault_queue.get(),
                    timeout=5.0
                )

                logger.info(f"Processing vault write for task {task_id} (queue size: {self.vault_queue.qsize()})")

                # Perform the vault update (this is the slow part - 10-30 seconds)
                from core.vault_writer import update_vault
                success = await update_vault(self.project_dir, task_id, task_data)

                if success:
                    logger.info(f"✅ Vault updated for {task_id}")
                else:
                    logger.warning(f"⚠️  Vault update failed for {task_id}")

                # Mark task as done in queue
                self.vault_queue.task_done()

            except asyncio.TimeoutError:
                # No items in queue, continue loop
                continue
            except asyncio.CancelledError:
                logger.info("Vault writer worker cancelled")
                break
            except Exception as e:
                logger.error(f"Error in vault writer worker: {e}", exc_info=True)

        logger.info("Vault writer worker stopped")

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

        # Start vault writer worker
        self.vault_worker_task = asyncio.create_task(self._vault_writer_worker())
        logger.info("Vault writer worker task created")

        iteration = 0
        last_cleanup = datetime.now()

        try:
            while not self.shutdown_requested:
                iteration += 1
                logger.debug(f"Execution loop iteration {iteration}")

                try:
                    # 1. Check for completed agents
                    completed = self.spawner.check_completed_agents()
                    if completed:
                        await self._handle_completed_agents(completed)

                    # 1.1. Periodic cleanup of leaked processes (every 60 seconds)
                    if (datetime.now() - last_cleanup).total_seconds() > 60:
                        self.spawner.cleanup_leaked_processes()
                        last_cleanup = datetime.now()

                    # 1.4. Update Living Codex for completed tasks
                    await self._update_codex_for_completed_tasks()

                    # 1.5. Check for tasks needing escalation
                    self._check_escalations()

                    # 1.6. Recover tasks with stale assignees
                    self._recover_stuck_assignees()

                    # 1.7. Terminate slow-exit processes (released baton but still running >15s)
                    self._terminate_slow_exit_processes()

                    # 1.8. Update retry counters for newly failed tasks
                    self._update_retry_counters()

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

    async def _update_codex_for_completed_tasks(self):
        """
        Update vault for tasks that recently completed.

        Tracks which tasks have been processed and updates vault for new completions.
        Falls back to legacy codex writer if vault doesn't exist.
        """
        try:
            # Track processed tasks in executor state
            if not hasattr(self, '_vault_processed_tasks'):
                # On first run, mark all ALREADY-DONE tasks as processed
                # (we only update vault for tasks that complete DURING this session)
                session = self.db.get_session()
                try:
                    from core.database import Task
                    already_done = session.query(Task).filter(Task.status == "done").all()
                    self._vault_processed_tasks = {task.id for task in already_done}
                    if self._vault_processed_tasks:
                        logger.info(
                            f"Initialized vault tracking with {len(self._vault_processed_tasks)} "
                            f"tasks that were already done before this session"
                        )
                finally:
                    session.close()
                # Don't return early - continue to process any newly completed tasks

            # Get tasks that just completed (status = done, not yet processed)
            session = self.db.get_session()
            try:
                from core.database import Task

                completed_tasks = session.query(Task).filter(
                    Task.status == "done"
                ).all()

                for task in completed_tasks:
                    # Skip if already processed
                    if task.id in self._vault_processed_tasks:
                        continue

                    task_data = {
                        'title': task.title,
                        'role': task.role,
                        'description': task.description
                    }

                    # Update vault
                    vault_dir = self.project_dir / ".relay" / "vault"
                    if vault_dir.exists():
                        logger.info(f"Updating vault for completed task {task.id}")
                        from core.vault_writer import update_vault, should_update_vault

                        # Check if this task should update vault
                        if not should_update_vault(task_data):
                            logger.info(f"Skipping vault update for {task.id} (QA/Security task)")
                            self._vault_processed_tasks.add(task.id)
                            continue

                        # Queue vault update (don't await - worker will process it)
                        try:
                            self.vault_queue.put_nowait((task.id, task_data))
                            self._vault_processed_tasks.add(task.id)
                            logger.info(f"Queued vault update for {task.id} (queue size: {self.vault_queue.qsize()})")
                        except asyncio.QueueFull:
                            logger.warning(f"⚠️  Vault queue full, will retry {task.id} next iteration")
                    else:
                        logger.warning(f"Vault directory not found at {vault_dir}. Run 'python3 .relay-framework/tools/migrate_to_vault.py .' to create vault structure.")
                        self._vault_processed_tasks.add(task.id)  # Skip this task

            finally:
                session.close()

        except Exception as e:
            logger.error(f"Failed to update codex for completed tasks: {e}")

    def _load_devops_tasks_template(self) -> list:
        """
        Load DevOps tasks from YAML template file.
        Falls back to embedded defaults if template file is missing.

        Returns:
            List of task dictionaries
        """
        template_path = Path(__file__).parent.parent / "templates" / "devops_tasks.yaml"

        try:
            if template_path.exists():
                with open(template_path, 'r') as f:
                    data = yaml.safe_load(f)
                    logger.info(f"Loaded {len(data['tasks'])} DevOps tasks from {template_path}")
                    return data['tasks']
            else:
                logger.warning(f"DevOps tasks template not found at {template_path}, using embedded defaults")
                return self._get_embedded_devops_tasks()
        except Exception as e:
            logger.error(f"Failed to load DevOps tasks template: {e}, using embedded defaults")
            return self._get_embedded_devops_tasks()

    def _get_embedded_devops_tasks(self) -> list:
        """
        Embedded DevOps tasks as fallback when template file is missing.

        Returns:
            List of task dictionaries
        """
        return [
            {
                "id": "DEVOPS-001",
                "title": "Create Dockerfile for application",
                "description": "Create Docker containerization setup (see template for full details)",
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
                "description": "Create continuous integration and deployment pipeline (see template for full details)",
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
                "description": "Setup environment configuration for different deployment environments (see template for full details)",
                "phase": "devops",
                "role": "devops_developer",
                "agent_type": "devops",
                "dependencies": [],
                "priority": 0,
                "complexity": 2,
                "status": "todo"
            }
        ]

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

                # Load DevOps tasks from YAML template
                devops_tasks = self._load_devops_tasks_template()

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
                    # Save original assignee before clearing
                    original_assignee = task.assignee
                    task.assignee = None
                    session.commit()

                    # Log recovery action with original assignee
                    self.db.log_action(
                        task_id=task.id,
                        agent_id="system",
                        action="recovered",
                        notes=f"Cleared stale assignee {original_assignee} - agent no longer running"
                    )

        except Exception as e:
            logger.error(f"Error recovering stuck assignees: {e}", exc_info=True)
        finally:
            session.close()

    def _update_retry_counters(self):
        """
        Update retry counters for tasks that have just failed.

        Increments retry_count and sets last_failed_at for tasks with
        status qa_failed or security_failed that haven't been updated yet.
        """
        session = self.db.get_session()
        try:
            from core.database import Task

            # Find failed tasks that need retry counter updates
            # (tasks where last_failed_at is None or older than updated_at)
            failed_tasks = session.query(Task).filter(
                Task.status.in_(["qa_failed", "security_failed"]),
                Task.assignee.is_(None)
            ).all()

            for task in failed_tasks:
                # Check if this is a NEW failure (last_failed_at is older than updated_at or None)
                if not task.last_failed_at or task.last_failed_at < task.updated_at:
                    task.retry_count += 1
                    task.last_failed_at = datetime.now()

                    logger.info(
                        f"Task {task.id} failed (retry {task.retry_count}/5). "
                        f"Next retry in {min(2 ** task.retry_count, 3600)}s"
                    )

                    session.commit()

        except Exception as e:
            logger.error(f"Error updating retry counters: {e}", exc_info=True)
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

            with self.spawner.running_agents_lock:
                running_agents_copy = list(self.spawner.running_agents.items())

            for agent_id, (process, task_id, start_time, log_handle) in running_agents_copy:
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
                    with self.spawner.running_agents_lock:
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
        - retry backoff period has elapsed (for failed tasks)

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
            now = datetime.now()

            for task in tasks:
                # Check if task has exceeded max retries
                if task.retry_count >= 5:
                    logger.warning(f"Task {task.id} exceeded max retries ({task.retry_count}), marking as permanently failed")
                    task.status = "failed"  # Permanently failed
                    session.commit()
                    continue

                # Check retry backoff for failed tasks
                if task.last_failed_at and task.retry_count > 0:
                    # Exponential backoff: 2^retry_count seconds, max 1 hour
                    backoff_seconds = min(2 ** task.retry_count, 3600)
                    elapsed = (now - task.last_failed_at).total_seconds()

                    if elapsed < backoff_seconds:
                        logger.debug(
                            f"Task {task.id} in backoff period "
                            f"(retry {task.retry_count}, {int(backoff_seconds - elapsed)}s remaining)"
                        )
                        continue

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
        Generate prompt for developer agent using two-layer architecture.

        Layer 1: Static system prompt (~800 tokens, reused)
        Layer 2: Dynamic task context (~600 tokens, per-task)

        Total: ~1,400 tokens (down from ~9,000)

        Args:
            task: Task to generate prompt for
            role: Developer role (frontend_developer or backend_developer)
            agent_id: Agent ID (e.g., "frontend_developer_1")
            agent_name: Human-readable agent name (e.g., "Maya")

        Returns:
            Prompt string
        """
        # === LAYER 1: Static System Prompt ===
        from core.system_prompts import get_system_prompt
        system_prompt = get_system_prompt(role, agent_name, agent_id)

        # === LAYER 2: Dynamic Task Context ===

        # 2a. Get Vault context (targeted, domain-specific)
        from core.vault_context import VaultContextManager

        if not hasattr(self, '_vault_manager'):
            self._vault_manager = VaultContextManager(self.project_dir)

        vault_context = self._vault_manager.get_context_for_agent(role, task.description or "")

        codex_section = ""
        if vault_context:
            codex_section = f"""
## 📖 What Is Already Built (Vault Context)

{vault_context}

**Note:** This is targeted context from the project vault. Read vault files directly for complete details.

---
"""
        else:
            logger.warning(
                f"Vault not found at {self.project_dir}/.relay/vault. "
                "Run 'python3 .relay-framework/tools/migrate_to_vault.py .' to create vault."
            )

        # 2b. Extract relevant context from planning docs
        from core.context_extractor import extract_relevant_context
        relevant_context = extract_relevant_context(
            self.project_dir,
            task.description or "",
            role
        )

        # 2c. Read task log if exists
        task_log_path = self.project_dir / ".relay" / "logs" / f"{task.id}.md"
        task_history = ""
        if task_log_path.exists():
            try:
                history_content = task_log_path.read_text()
                # Cap at 2000 chars to avoid bloat
                if len(history_content) > 2000:
                    history_content = history_content[:2000] + "\n\n[... truncated, read full file for complete history]"
                task_history = f"""
## 📜 Task History

{history_content}

**Note:** This task has prior work. Read carefully to avoid repeating mistakes.

---
"""
            except Exception:
                pass

        # === COMBINE: System Prompt + Task Context ===

        # Avoid duplicating task description if it's in the history
        task_desc_section = ""
        if not task_history:
            # First run - no history yet, show description
            task_desc_section = f"""
**Task Description**:
{task.description or '[Read from database]'}

**Current Status**: `{task.status}`
"""

        # Generate vault update instructions for this task
        from core.vault_instructions import get_vault_update_section
        vault_update_instructions = get_vault_update_section(task.description or "", self.project_dir)

        # Count tokens for observability
        from core.token_counter import count_prompt_components, format_token_report
        token_counts = count_prompt_components(
            system_prompt=system_prompt,
            vault_context=vault_context,
            planning_context=relevant_context,
            task_history=task_history,
            task_description=task.description or ""
        )
        logger.info(f"Generated prompt for {task.id} ({role}): {format_token_report(token_counts)}")

        return f"""{system_prompt}

---

# TASK: {task.id}

{task_desc_section}{task_history}{codex_section}

## Relevant Planning Context

{relevant_context}

{vault_update_instructions}

**Note:** Read full files if needed: `.relay/vault/planning/system_design.md`, `.relay/vault/planning/security_policy.md`, `.relay/vault/planning/ui_standards.md`
"""

    def _extract_recent_changes(self, task_log_content: str) -> str:
        """
        Extract the most recent development work from task log.

        Looks for the last "Development Completed" section to show QA
        what the developer just did.

        Args:
            task_log_content: Full task log content

        Returns:
            Recent changes summary or empty string
        """
        # Look for last "Development Completed" or "Development Started" section
        lines = task_log_content.split('\n')
        recent_section = []
        in_recent_section = False

        # Scan backwards to find the most recent dev work
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i]

            # Found end of a section (next section's header)
            if line.startswith('###') and in_recent_section:
                break

            # Found development completed section
            if 'Development Completed' in line or 'Development Started' in line:
                in_recent_section = True

            if in_recent_section:
                recent_section.insert(0, line)

        if recent_section:
            return '\n'.join(recent_section[:30])  # Limit to 30 lines
        return ""

    def _generate_qa_prompt(self, task: Task, agent_id: str, agent_name: str) -> str:
        """
        Generate QA prompt using two-layer architecture.

        Args:
            task: Task to generate QA prompt for
            agent_id: Agent ID (e.g., "qa_1")
            agent_name: Human-readable agent name (e.g., "Sarah")

        Returns:
            QA prompt string
        """
        # === LAYER 1: Static System Prompt ===
        from core.system_prompts import get_system_prompt
        system_prompt = get_system_prompt("qa", agent_name, agent_id)

        # === LAYER 2: Dynamic Task Context ===

        # 2a. Get Vault context (targeted for QA)
        from core.vault_context import VaultContextManager

        if not hasattr(self, '_vault_manager'):
            self._vault_manager = VaultContextManager(self.project_dir)

        vault_context = self._vault_manager.get_context_for_agent("qa", task.description or "")

        codex_section = ""
        if vault_context:
            codex_section = f"""
## 📖 What Exists (Vault Context)

{vault_context}

---
"""
        else:
            logger.warning(
                f"Vault not found for QA agent. "
                "Run 'python3 .relay-framework/tools/migrate_to_vault.py .' to create vault."
            )

        # 2b. Read task log and extract recent changes
        task_log_path = self.project_dir / ".relay" / "logs" / f"{task.id}.md"
        task_history = ""
        recent_changes_section = ""

        if task_log_path.exists():
            try:
                history_content = task_log_path.read_text()

                # Extract recent developer changes for QA to review
                recent_changes = self._extract_recent_changes(history_content)
                if recent_changes:
                    recent_changes_section = f"""
## 🔨 Recently Completed Changes (from previous developer)

The developer agent just completed this task and made the following changes:

{recent_changes}

**Your job:** Verify these changes work correctly and meet the acceptance criteria.

---
"""

                # Full history for context
                if len(history_content) > 2000:
                    history_content = history_content[:2000] + "\n\n[... truncated]"
                task_history = f"""
## 📜 Full Task History

{history_content}

---
"""
            except Exception:
                pass

        # 2c. Show task description for first-time tasks
        task_desc_section = ""
        if not task_history:
            task_desc_section = f"""

**Title:** {task.title or 'Unknown'}

**Requirements:**
{task.description or '[No description provided in database]'}

**Current Status:** `{task.status}`

---

"""

        # Extract relevant context from planning docs
        from core.context_extractor import extract_relevant_context
        relevant_context = extract_relevant_context(
            self.project_dir,
            task.description or "",
            "qa"
        )

        # Count tokens for observability
        from core.token_counter import count_prompt_components, format_token_report
        token_counts = count_prompt_components(
            system_prompt=system_prompt,
            vault_context=vault_context,
            planning_context=relevant_context,
            task_history=task_history,
            task_description=task.description or ""
        )
        logger.info(f"Generated QA prompt for {task.id}: {format_token_report(token_counts)}")

        return f"""{system_prompt}

---

# TASK: {task.id}

{task_desc_section}{recent_changes_section}{task_history}{codex_section}

## Relevant Planning Context

{relevant_context}
"""


    def _generate_security_prompt(self, task: Task, agent_id: str, agent_name: str) -> str:
        """
        Generate prompt for Security agent.

        Uses two-layer architecture:
        - Layer 1: Static system prompt from system_prompts.py
        - Layer 2: Dynamic task context (vault + planning docs + history)

        Args:
            task: Task to generate Security prompt for
            agent_id: Agent ID (e.g., "security_1")
            agent_name: Human-readable agent name (e.g., "Alex")

        Returns:
            Security prompt string
        """
        # === LAYER 1: Static System Prompt ===
        from core.system_prompts import get_system_prompt
        system_prompt = get_system_prompt("security", agent_name, agent_id)

        # === LAYER 2: Dynamic Task Context ===

        # 2a. Get Vault context for Security agent
        from core.vault_context import VaultContextManager

        if not hasattr(self, '_vault_manager'):
            self._vault_manager = VaultContextManager(self.project_dir)

        vault_context = self._vault_manager.get_context_for_agent("security", task.description or "")

        codex_section = ""
        if vault_context:
            codex_section = f"""
## 📖 Security Standards & Architecture (Vault Context)

{vault_context}

---
"""

        # 2b. Extract relevant context from security policy
        from core.context_extractor import extract_relevant_context
        relevant_context = extract_relevant_context(
            self.project_dir,
            task.description or "",
            "security"
        )

        planning_section = ""
        if relevant_context:
            planning_section = f"""
## 📋 Security Policy Reference

{relevant_context}

---
"""

        # 2c. Read task log and extract recent changes
        task_log_path = self.project_dir / ".relay" / "logs" / f"{task.id}.md"
        task_history = ""
        recent_changes_section = ""

        if task_log_path.exists():
            try:
                history_content = task_log_path.read_text()

                # Extract recent developer changes for Security to review
                recent_changes = self._extract_recent_changes(history_content)
                if recent_changes:
                    recent_changes_section = f"""
## 🔨 Recently Completed Changes

The developer just completed this task. Review these changes for security vulnerabilities:

{recent_changes}

---
"""

                # Full history for context
                if len(history_content) > 2000:
                    history_content = history_content[:2000] + "\n\n[... truncated, read full file for complete history]"
                task_history = f"""
## 📜 Task History

{history_content}

**Note:** This task has prior work. Review to understand the context.

---
"""
            except Exception:
                pass

        # 2d. Task description
        task_desc_section = ""
        if not task_history:
            task_desc_section = f"""
**Task Description**:
{task.description or '[Read from database]'}

**Current Status**: `{task.status}`
"""

        # === COMBINE: System Prompt + Task Context ===

        return f"""{system_prompt}

---

# TASK: {task.id}

{task_desc_section}{recent_changes_section}{task_history}{codex_section}{planning_section}

## Your Assignment

Read task details from `.relay/tasks.db`:
```sql
SELECT * FROM tasks WHERE id = '{task.id}'
```

Perform a security scan on the implementation.
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

        Uses two-layer architecture:
        - Layer 1: Static system prompt from system_prompts.py
        - Layer 2: Dynamic task context (vault + planning docs + history)

        Args:
            task: Task to generate prompt for
            agent_id: Agent ID (e.g., "devops_1")
            agent_name: Human-readable agent name (e.g., "Docker")

        Returns:
            DevOps prompt string
        """
        # === LAYER 1: Static System Prompt ===
        from core.system_prompts import get_system_prompt
        system_prompt = get_system_prompt("devops", agent_name, agent_id)

        # === LAYER 2: Dynamic Task Context ===

        # 2a. Get Vault context (targeted, domain-specific)
        from core.vault_context import VaultContextManager

        if not hasattr(self, '_vault_manager'):
            self._vault_manager = VaultContextManager(self.project_dir)

        vault_context = self._vault_manager.get_context_for_agent("devops", task.description or "")

        codex_section = ""
        if vault_context:
            codex_section = f"""
## 📖 Current Infrastructure State (Vault Context)

{vault_context}

**Note:** This shows current infrastructure. Read vault files for complete details.

---
"""

        # 2b. Extract relevant context from planning docs
        from core.context_extractor import extract_relevant_context
        relevant_context = extract_relevant_context(
            self.project_dir,
            task.description or "",
            "devops"
        )

        planning_section = ""
        if relevant_context:
            planning_section = f"""
## 📋 System Design Reference

{relevant_context}

---
"""

        # 2c. Read task log if exists (previous attempts)
        task_log_path = self.project_dir / ".relay" / "logs" / f"{task.id}.md"
        task_history = ""
        if task_log_path.exists():
            try:
                history_content = task_log_path.read_text()
                if len(history_content) > 2000:
                    history_content = history_content[:2000] + "\n\n[... truncated, read full file for complete history]"
                task_history = f"""
## 📜 Task History

{history_content}

**Note:** This task has prior attempts. Review to avoid repeating mistakes.

---
"""
            except Exception:
                pass

        # 2d. Task description
        task_desc_section = ""
        if not task_history:
            task_desc_section = f"""
**Task Description**:
{task.description or '[Read from database]'}

**Current Status**: `{task.status}`
"""

        # === COMBINE: System Prompt + Task Context ===

        return f"""{system_prompt}

---

# TASK: {task.id}

{task_desc_section}{task_history}{codex_section}{planning_section}

## Your Assignment

Read task details from `.relay/tasks.db`:
```sql
SELECT * FROM tasks WHERE id = '{task.id}'
```

The description field contains infrastructure/deployment requirements.
"""

    def _generate_database_prompt(self, task: Task, agent_id: str, agent_name: str) -> str:
        """
        Generate prompt for Database agent (migration generation).

        Uses two-layer architecture:
        - Layer 1: Static system prompt from system_prompts.py
        - Layer 2: Dynamic task context (vault + planning docs + history)

        Args:
            task: Task to generate prompt for
            agent_id: Agent ID (e.g., "database_1")
            agent_name: Human-readable agent name (e.g., "Schema")

        Returns:
            Database prompt string
        """
        # === LAYER 1: Static System Prompt ===
        from core.system_prompts import get_system_prompt
        system_prompt = get_system_prompt("database", agent_name, agent_id)

        # === LAYER 2: Dynamic Task Context ===

        # 2a. Get Vault context (targeted, domain-specific)
        from core.vault_context import VaultContextManager

        if not hasattr(self, '_vault_manager'):
            self._vault_manager = VaultContextManager(self.project_dir)

        vault_context = self._vault_manager.get_context_for_agent("database", task.description or "")

        codex_section = ""
        if vault_context:
            codex_section = f"""
## 📖 Current Database Schema (Vault Context)

{vault_context}

**Note:** This shows current schema state. Read vault files for complete details.

---
"""

        # 2b. Extract relevant context from planning docs
        from core.context_extractor import extract_relevant_context
        relevant_context = extract_relevant_context(
            self.project_dir,
            task.description or "",
            "database"
        )

        planning_section = ""
        if relevant_context:
            planning_section = f"""
## 📋 System Design Reference

{relevant_context}

---
"""

        # 2c. Read task log if exists (previous migration attempts)
        task_log_path = self.project_dir / ".relay" / "logs" / f"{task.id}.md"
        task_history = ""
        if task_log_path.exists():
            try:
                history_content = task_log_path.read_text()
                if len(history_content) > 2000:
                    history_content = history_content[:2000] + "\n\n[... truncated, read full file for complete history]"
                task_history = f"""
## 📜 Task History

{history_content}

**Note:** This task has prior attempts. Review to avoid repeating mistakes.

---
"""
            except Exception:
                pass

        # 2d. Task description
        task_desc_section = ""
        if not task_history:
            task_desc_section = f"""
**Task Description**:
{task.description or '[Read from database]'}

**Current Status**: `{task.status}`
"""

        # === COMBINE: System Prompt + Task Context ===

        return f"""{system_prompt}

---

# TASK: {task.id}

{task_desc_section}{task_history}{codex_section}{planning_section}

## Your Assignment

Read task details from `.relay/tasks.db`:
```sql
SELECT * FROM tasks WHERE id = '{task.id}'
```

The description field explains what schema changes need migration files.
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
