"""
Task Escalation System
=======================

Tracks task failure cycles and escalates after repeated QA/Security failures.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TaskEscalation:
    """
    Tracks and escalates tasks that repeatedly fail QA or Security reviews.

    After N failures, creates a review task or alerts for manual intervention.
    """

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.max_failures_before_escalation = 3

    def check_failure_count(self, task_id: str, db) -> dict:
        """
        Count how many times this task has failed QA or Security.

        Args:
            task_id: Task ID to check
            db: TaskDatabase instance

        Returns:
            Dict with {qa_failures: int, security_failures: int, should_escalate: bool}
        """
        try:
            # Count failure logs
            session = db.get_session()
            from core.database import TaskLog

            qa_failures = session.query(TaskLog).filter(
                TaskLog.task_id == task_id,
                TaskLog.action == "qa_failed"
            ).count()

            security_failures = session.query(TaskLog).filter(
                TaskLog.task_id == task_id,
                TaskLog.action == "security_failed"
            ).count()

            total_failures = qa_failures + security_failures
            should_escalate = total_failures >= self.max_failures_before_escalation

            session.close()

            return {
                "qa_failures": qa_failures,
                "security_failures": security_failures,
                "total_failures": total_failures,
                "should_escalate": should_escalate
            }

        except Exception as e:
            logger.error(f"Failed to check failure count for {task_id}: {e}")
            return {
                "qa_failures": 0,
                "security_failures": 0,
                "total_failures": 0,
                "should_escalate": False
            }

    def escalate_task(self, task_id: str, failure_info: dict, db) -> Optional[str]:
        """
        Escalate a task after repeated failures.

        Creates a REVIEW task for manual investigation.

        Args:
            task_id: Task that repeatedly failed
            failure_info: Failure count info from check_failure_count()
            db: TaskDatabase instance

        Returns:
            Review task ID if created, None otherwise
        """
        try:
            review_task_id = f"REVIEW-{task_id}"

            # Check if review task already exists
            existing = db.get_task(review_task_id)
            if existing:
                logger.debug(f"Review task {review_task_id} already exists")
                return None

            # Get original task
            task = db.get_task(task_id)
            if not task:
                logger.error(f"Cannot escalate - task {task_id} not found")
                return None

            # Create review task
            review_task = {
                "id": review_task_id,
                "title": f"Manual Review Required: {task.title}",
                "description": f"""**⚠️ ESCALATION REQUIRED**

Task {task_id} has failed {failure_info['total_failures']} times:
- QA failures: {failure_info['qa_failures']}
- Security failures: {failure_info['security_failures']}

**Original Task:** {task.title}

**Required Actions:**
1. Read `.relay/logs/{task_id}.md` to understand the full failure history
2. Review all QA and Security feedback
3. Identify root cause of repeated failures:
   - Is the task description unclear?
   - Are acceptance criteria too vague?
   - Is there a fundamental design issue?
   - Are QA/Security requirements unrealistic?

4. Decide on resolution:
   - **Option A: Fix and Retry**
     * Make necessary code fixes
     * Update task description if unclear
     * Reset task status to 'todo'

   - **Option B: Split Task**
     * Break into smaller, more focused tasks
     * Mark original task as 'blocked' or 'cancelled'

   - **Option C: Escalate to Human**
     * Document blocking issue
     * Request manual intervention

5. Document decision and actions in `.relay/logs/{review_task_id}.md`

**Notes:**
- This task requires manual human review
- Original task {task_id} is blocked until this review completes

References: docs/system_design.md, docs/security_policy.md, docs/ui_standards.md
""",
                "phase": task.phase,
                "role": "manual_review",  # Requires human intervention
                "agent_type": "manual",
                "dependencies": [],
                "priority": task.priority + 10,  # Very high priority
                "complexity": 3,
                "status": "todo"
            }

            db.create_task(review_task)

            # Block original task
            db.update_task(task_id, {
                "status": "blocked",
                "priority": 0  # Lower priority
            })

            logger.warning(
                f"⚠️  Task {task_id} escalated after {failure_info['total_failures']} failures. "
                f"Created review task: {review_task_id}"
            )

            db.log_action(
                task_id=review_task_id,
                agent_id="system",
                action="escalation_created",
                notes=f"Task {task_id} escalated after {failure_info['total_failures']} failures"
            )

            db.log_action(
                task_id=task_id,
                agent_id="system",
                action="escalated",
                status="blocked",
                notes=f"Task blocked for manual review - see {review_task_id}"
            )

            return review_task_id

        except Exception as e:
            logger.error(f"Failed to escalate task {task_id}: {e}")
            import traceback
            traceback.print_exc()
            return None
