"""
Request Agent
=============

Handles new features, bugs, improvements, and chores for existing projects.
Single unified entry point that reads existing docs, updates them if needed,
and generates executable tasks.

Usage:
    relay request "Add user profile editing with avatar upload"
    relay request "Bug: Login fails with uppercase emails"
    relay request "Feature: Add Stripe payment integration"
"""

import subprocess
import logging
import json
from pathlib import Path
from datetime import datetime
from .config import get_model_id_for_agent

logger = logging.getLogger(__name__)

REQUEST_AGENT_PROMPT = """# Relay Request Agent

You are analyzing a user request for an existing software project and breaking it down into executable tasks.

**User Request:**
{user_request}

**Existing Project Context:**
- System Design: [READ docs/system_design.md]
- Security Policy: [READ docs/security_policy.md]
- UI Standards: [READ docs/ui_standards.md]
- Current Master Plan: [READ docs/master_plan.md]
- Completed Tasks: {completed_task_count} tasks done
- Last Task ID used: {last_task_id}

**Your job — complete ALL steps in order:**

## STEP 1: Classify Request
Determine type: feature | bug | improvement | chore
- feature: new capability that doesn't exist yet
- bug: something broken that needs fixing
- improvement: existing feature that needs enhancement
- chore: tech debt, refactoring, dependency updates

## STEP 2: Impact Analysis
Answer these questions:
- Does this require new database tables or schema changes?
- Does this add new API endpoints or change existing ones?
- Does this introduce new UI patterns not in ui_standards.md?
- Does this have security implications (auth, payments, PII)?
- Which existing features/tasks does this touch?

## STEP 3: Update Critical Docs (ONLY if needed)
If impact analysis found changes needed:
- **APPEND** new sections to docs/system_design.md (never overwrite existing sections)
- **APPEND** new security rules to docs/security_policy.md (if security impact)
- **APPEND** new UI patterns to docs/ui_standards.md (if new UI patterns)
- **APPEND** to docs/master_plan.md under a new section heading

**CRITICAL:** Only APPEND. Never overwrite or delete existing content.

If no doc updates needed, SKIP this step entirely.

## STEP 4: Generate Tasks
Write .relay/request_tasks.json with tasks starting from ID: {next_task_id}

**Task Pipeline Rules:**
- bug fixes: [backend_developer or frontend_developer] → [qa] → [security if auth-related]
- new features: [architect if complex] → [backend_developer] → [frontend_developer] → [qa] → [security if sensitive]
- improvements: skip architect, go straight to developer → qa
- chores: developer only (no qa/security unless critical)

**Task Requirements:**
- Each description must be 200+ characters
- Must reference relevant docs (docs/system_design.md, docs/security_policy.md, docs/ui_standards.md)
- Must include acceptance criteria
- Set dependencies correctly — qa tasks must depend on their developer task
- Frontend tasks must reference docs/ui_standards.md
- Security-sensitive tasks must reference docs/security_policy.md

JSON Format:
{{
  "request_type": "feature|bug|improvement|chore",
  "user_request": "{user_request}",
  "timestamp": "{timestamp}",
  "tasks": [
    {{
      "id": "{next_task_id}",
      "title": "Short task title",
      "description": "Detailed description (200+ chars) referencing docs...",
      "phase": "feature_additions|bug_fixes|improvements|maintenance",
      "role": "backend_developer|frontend_developer|qa|security|architect",
      "agent_type": "backend|frontend|qa|security|architect",
      "dependencies": [],
      "priority": 3,
      "complexity": 3
    }}
  ]
}}

## STEP 5: Write Summary
Write .relay/request_summary.md with:
- Request classification (feature/bug/improvement/chore)
- Doc sections updated (list each file + section added, or "None")
- Task breakdown (ID, title, assignee, estimated complexity)
- Total task count
- Overall complexity estimate

Use this format:
```markdown
# Request Summary

**Request:** {user_request}
**Type:** [feature|bug|improvement|chore]
**Generated:** {timestamp}

## Documentation Updates
[List each file and section appended, or "None - no doc changes needed"]

## Task Breakdown
Total: X tasks, estimated Y story points

1. [TASK-ID] Task Title
   - Assignee: role_name
   - Complexity: N/5
   - Dependencies: [list or "None"]

## Approval Required
Review the tasks above and the request_tasks.json file.
Changes to documentation have already been saved.
```

**Remember:**
- Follow existing tech stack (don't introduce new frameworks)
- Reference security policy for auth/data handling
- Follow UI standards for any frontend work
- Set realistic complexity and proper dependencies
- Keep docs/master_plan.md coherent
"""


def run_request_agent(project_dir: Path, user_request: str) -> bool:
    """
    Run request agent to analyze user request and generate tasks.

    Args:
        project_dir: Project directory
        user_request: User's feature/bug/improvement request

    Returns:
        True if successful and user approved, False otherwise
    """
    project_dir = Path(project_dir)

    print("\n" + "="*80)
    print("🎯 REQUEST AGENT")
    print("="*80)
    print(f"\nRequest: {user_request}\n")

    # Check that project is initialized
    relay_dir = project_dir / ".relay"
    if not relay_dir.exists():
        logger.error("No Relay project found. Run 'relay start' first.")
        return False

    docs_dir = project_dir / "docs"
    required_docs = [
        docs_dir / "system_design.md",
        docs_dir / "security_policy.md",
        docs_dir / "ui_standards.md",
        docs_dir / "master_plan.md"
    ]

    missing_docs = [doc for doc in required_docs if not doc.exists()]
    if missing_docs:
        logger.error(f"Missing planning documents: {[str(d) for d in missing_docs]}")
        logger.error("Run 'relay analyze' or 'relay start' to generate them.")
        return False

    # Get task database info
    try:
        from .database import TaskDatabase
        db = TaskDatabase(project_dir)

        stats = db.get_statistics()
        last_task_id = _get_last_task_id(db)
        next_task_id = _generate_next_task_id(last_task_id)

    except Exception as e:
        logger.error(f"Failed to read task database: {e}")
        return False

    # Store original doc sizes for append-only validation
    original_sizes = {}
    for doc in required_docs:
        if doc.exists():
            original_sizes[str(doc)] = doc.stat().st_size

    # Build prompt
    timestamp = datetime.now().isoformat()
    prompt = REQUEST_AGENT_PROMPT.format(
        user_request=user_request,
        completed_task_count=stats['completed'],
        last_task_id=last_task_id,
        next_task_id=next_task_id,
        timestamp=timestamp
    )

    # Spawn Claude CLI
    model_id = get_model_id_for_agent('request_agent')

    try:
        print("Analyzing request and generating tasks...\n")

        process = subprocess.Popen(
            [
                "claude",
                "--model", model_id,
                "--dangerously-skip-permissions",
                prompt
            ],
            cwd=str(project_dir),
            stdout=None,  # Stream to terminal
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL
        )

        _, stderr = process.communicate(timeout=900)  # 15-minute timeout
        returncode = process.returncode

        if returncode != 0:
            error_output = stderr.decode()[:2000] if stderr else "No error output"
            logger.error(f"Request agent failed with exit code {returncode}")
            logger.error(f"Stderr: {error_output}")
            return False

        # Validate append-only doc updates
        if not _validate_doc_updates(required_docs, original_sizes):
            logger.error("Doc validation failed - agent may have overwritten content")
            return False

        # Verify output files created
        summary_file = project_dir / ".relay/request_summary.md"
        tasks_file = project_dir / ".relay/request_tasks.json"

        if not summary_file.exists() or not tasks_file.exists():
            logger.error("Request agent did not produce output files")
            return False

        # Validate tasks JSON
        try:
            with open(tasks_file, 'r') as f:
                tasks_data = json.load(f)

            if not tasks_data.get('tasks'):
                logger.error("request_tasks.json contains no tasks")
                return False

            # Validate task quality (warnings only)
            validation_warnings = _validate_task_quality(tasks_data['tasks'])
            if validation_warnings:
                logger.warning("⚠️  Task quality warnings:")
                for warning in validation_warnings[:5]:
                    logger.warning(f"  - {warning}")
                if len(validation_warnings) > 5:
                    logger.warning(f"  ... and {len(validation_warnings) - 5} more")

            logger.info(f"✅ Generated {len(tasks_data['tasks'])} tasks")

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Invalid request_tasks.json format: {e}")
            return False

        # === USER APPROVAL PHASE ===
        return _approval_flow(project_dir, db, summary_file, tasks_file)

    except subprocess.TimeoutExpired:
        logger.error("Request agent timed out (15-minute limit)")
        return False
    except Exception as e:
        logger.error(f"Request agent failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def _approval_flow(project_dir: Path, db, summary_file: Path, tasks_file: Path) -> bool:
    """Show summary and get user approval."""

    print("\n" + "="*80)
    print("📋 REQUEST SUMMARY")
    print("="*80 + "\n")

    # Show the summary
    print(summary_file.read_text())

    print("\n" + "="*80)
    print("\nOptions:")
    print("  1. Approve — append tasks to tasks.db and start execution")
    print("  2. Edit   — open request_tasks.json to modify before approving")
    print("  3. Cancel — discard tasks (doc changes if any are already saved)")
    print()

    while True:
        choice = input("Your choice (1/2/3): ").strip()

        if choice == "1":
            # Merge into tasks.db
            logger.info("Appending tasks to database...")
            success = _merge_tasks_into_database(project_dir, db, tasks_file)

            if success:
                # Archive files for record-keeping
                archive_name = f"request_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                (project_dir / ".relay/request_tasks.json").rename(
                    project_dir / ".relay" / f"{archive_name}_tasks.json"
                )
                (project_dir / ".relay/request_summary.md").rename(
                    project_dir / ".relay" / f"{archive_name}_summary.md"
                )
                print(f"\n✅ Tasks added! Archived to .relay/{archive_name}_*")
                return True
            else:
                logger.error("Failed to append tasks to database")
                return False

        elif choice == "2":
            print("\nOpening request_tasks.json in editor...")
            print("Edit the tasks, save, and run command again to review.")
            subprocess.run(["open", str(tasks_file)])
            return False

        elif choice == "3":
            print("\nTasks discarded.")
            print("Note: any doc updates were already saved.")
            tasks_file.unlink(missing_ok=True)
            summary_file.unlink(missing_ok=True)
            return False

        else:
            print("Invalid choice. Please enter 1, 2, or 3.")


def _validate_doc_updates(required_docs: list, original_sizes: dict) -> bool:
    """
    Ensure docs were only appended to, not overwritten.

    Args:
        required_docs: List of doc paths
        original_sizes: Dict mapping path to original size in bytes

    Returns:
        True if validation passed
    """
    for doc in required_docs:
        if not doc.exists():
            continue

        doc_str = str(doc)
        if doc_str not in original_sizes:
            continue

        original_size = original_sizes[doc_str]
        current_size = doc.stat().st_size

        # If file shrunk by more than 10%, likely overwritten
        if current_size < original_size * 0.9:
            logger.error(f"{doc.name} appears to have been overwritten (was {original_size} bytes, now {current_size})")
            return False

    return True


def _get_last_task_id(db) -> str:
    """Get the highest task ID from database."""
    try:
        session = db.get_session()
        tasks = session.query(db.Task.id).all()

        if not tasks:
            return "TASK-000"

        max_num = 0
        max_prefix = "TASK"

        for (task_id,) in tasks:
            # Extract numeric part from IDs like "ARC-001", "FEAT-005"
            parts = task_id.split('-')
            if len(parts) == 2:
                try:
                    num = int(parts[1])
                    if num > max_num:
                        max_num = num
                        max_prefix = parts[0]
                except ValueError:
                    continue

        return f"{max_prefix}-{max_num:03d}"

    except Exception as e:
        logger.warning(f"Could not determine last task ID: {e}")
        return "TASK-000"


def _generate_next_task_id(last_task_id: str) -> str:
    """Generate next task ID for new request."""
    try:
        parts = last_task_id.split('-')
        if len(parts) == 2:
            num = int(parts[1])
            # Use REQ prefix for request-generated tasks
            return f"REQ-{num+1:03d}"
    except (ValueError, IndexError):
        pass

    return "REQ-001"


def _merge_tasks_into_database(project_dir: Path, db, tasks_file: Path) -> bool:
    """
    Merge request tasks into existing tasks database.

    Args:
        project_dir: Project directory
        db: TaskDatabase instance
        tasks_file: Path to request_tasks.json

    Returns:
        True if successful
    """
    try:
        with open(tasks_file, 'r') as f:
            tasks_data = json.load(f)

        for task_data in tasks_data['tasks']:
            # Ensure required fields
            if 'status' not in task_data:
                task_data['status'] = 'todo'

            # Ensure agent_type is set
            if 'agent_type' not in task_data:
                role = task_data.get('role', '')
                if 'frontend' in role.lower():
                    task_data['agent_type'] = 'frontend'
                elif 'qa' in role.lower():
                    task_data['agent_type'] = 'qa'
                elif 'security' in role.lower():
                    task_data['agent_type'] = 'security'
                elif 'architect' in role.lower():
                    task_data['agent_type'] = 'architect'
                else:
                    task_data['agent_type'] = 'backend'

            # Create task
            db.create_task(task_data)
            logger.info(f"Added task: {task_data['id']} - {task_data['title']}")

        stats = db.get_statistics()
        logger.info(f"Database now has {stats['total']} total tasks")
        return True

    except Exception as e:
        logger.error(f"Failed to merge tasks: {e}")
        import traceback
        traceback.print_exc()
        return False


def _validate_task_quality(tasks: list) -> list:
    """
    Validate task description quality.
    Returns list of warning messages (non-blocking).
    """
    warnings = []

    for idx, task_data in enumerate(tasks):
        task_id = task_data.get('id', f'task-{idx}')
        desc = task_data.get('description', '')

        # Short description
        if len(desc) < 200:
            warnings.append(
                f"{task_id}: Short description ({len(desc)} chars, recommend 200+)"
            )

        # Missing doc references
        doc_refs = ['docs/system_design', 'docs/security_policy', 'docs/ui_standards']
        if not any(ref in desc for ref in doc_refs):
            warnings.append(f"{task_id}: No doc references")

        # Missing acceptance criteria
        if 'acceptance' not in desc.lower() and 'criteria' not in desc.lower():
            warnings.append(f"{task_id}: No acceptance criteria")

        # Frontend tasks should reference UI standards
        role = task_data.get('role', '')
        if 'frontend' in role.lower() and 'ui_standards' not in desc:
            warnings.append(f"{task_id}: Frontend task missing UI standards ref")

        # Security-sensitive tasks
        security_keywords = ['auth', 'login', 'password', 'encrypt', 'permission', 'token']
        if any(kw in desc.lower() for kw in security_keywords) and 'security_policy' not in desc:
            warnings.append(f"{task_id}: Security task missing security policy ref")

    return warnings
