"""
Living Codex Writer
===================

Maintains docs/codex.md - a present-tense source of truth that grows as tasks complete.
Updates after every completed task to reflect what was actually built.

The Codex answers: "What is built and working right now?"
NOT "What will be built?" (that's master_plan.md)
"""

import subprocess
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

CODEX_UPDATE_PROMPT = """# Codex Writer

You just completed this task:
**Task ID:** {task_id}
**Title:** {task_title}
**Role:** {agent_role}

**What was built (from task log):**
{task_output_summary}

**Current Codex:**
{current_codex}

---

**Your job:**
Update `docs/codex.md` to reflect what was JUST built in this task.

**CRITICAL RULES:**
1. **Present tense only** - "The API has", "Users can", "The database contains"
2. **Facts only** - What exists NOW, not what's planned
3. **Append to relevant sections** - Don't delete existing entries
4. **If this is a refactor/update** - Update the existing entry in place
5. **Use tables and bullets** - Keep it scannable
6. **Never include:** task IDs, phase names, future plans, "will", "todo"

**Sections to maintain:**
- **Tech Stack** - Languages, frameworks, libraries actually in use
- **Database** - Tables that exist with real schemas
- **API Endpoints** - Routes that work (method, path, auth, description)
- **Frontend** - Pages and components that exist
- **Integrations** - External services configured
- **Security** - Actual security measures implemented
- **Environment Variables** - Required env vars
- **Test Coverage** - Real test counts and coverage

**What to update based on task type:**
- Backend task → Update API Endpoints, Database, or Integrations
- Frontend task → Update Frontend pages/components
- Database task → Update Database migrations
- Security task → Update Security measures
- DevOps task → Update Tech Stack, Environment Variables

**Update format:**
- If section doesn't exist yet, create it
- If entry exists, update it in place
- Add timestamp at top: "Last updated: {timestamp} by task {task_id}"
- Use tables for structured data (APIs, DB tables, routes)
- Use bullets for lists (components, security measures)

Use the Write tool to save the full updated codex to `docs/codex.md`.
"""

INITIAL_CODEX_TEMPLATE = """# Project Codex
> Living source of truth for what is built. Updated automatically after each completed task.
> Last updated: {timestamp} (initialized)

---

## Tech Stack
*Tech stack will be populated as tasks complete*

---

## Database
### Tables
*Database tables will be documented as they're created*

### Migrations
*Migration files will be listed as they're added*

---

## API Endpoints
*API endpoints will be documented as they're implemented*

---

## Frontend
### Pages
*Frontend pages will be documented as they're built*

### Shared Components
*Reusable components will be listed as they're created*

---

## Integrations
*Third-party integrations will be documented as they're configured*

---

## Security
*Security measures will be listed as they're implemented*

---

## Environment Variables Required
*Environment variables will be documented as they're added*

---

## Test Coverage
*Test metrics will be updated as tests are written*

---
"""


async def update_codex(project_dir: Path, task_id: str, task_data: dict) -> bool:
    """
    Update the Living Codex after a task completes.

    Called by orchestrator after every task reaches 'done' status.

    Args:
        project_dir: Project directory
        task_id: Completed task ID
        task_data: Task data dict with title, role, description

    Returns:
        True if update successful, False otherwise
    """
    try:
        codex_path = project_dir / "docs" / "codex.md"

        # Initialize codex if first task
        if not codex_path.exists():
            logger.info("Initializing Living Codex (docs/codex.md)")
            codex_path.parent.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d %I:%M %p")
            codex_path.write_text(INITIAL_CODEX_TEMPLATE.format(timestamp=timestamp))

        # Read task log to get summary of work done
        task_log_path = project_dir / ".relay" / "logs" / f"{task_id}.md"
        if task_log_path.exists():
            task_output_summary = task_log_path.read_text()[:3000]  # Cap to avoid overflow
        else:
            task_output_summary = f"Task completed: {task_data.get('title', 'Unknown')}"

        # Read current codex
        current_codex = codex_path.read_text()

        # Build update prompt
        timestamp = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        prompt = CODEX_UPDATE_PROMPT.format(
            task_id=task_id,
            task_title=task_data.get('title', 'Unknown'),
            agent_role=task_data.get('role', 'Unknown'),
            task_output_summary=task_output_summary,
            current_codex=current_codex,
            timestamp=timestamp
        )

        # Get model for codex writer
        from .config import get_model_id_for_agent, load_project_config
        try:
            config = load_project_config(project_dir)
            model_id = get_model_id_for_agent('codex_writer', config)
        except Exception:
            # Fall back to default (Sonnet)
            model_id = 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'

        logger.info(f"Updating Living Codex for completed task {task_id}...")

        # Run codex writer as short Claude session (5 min timeout)
        process = subprocess.Popen(
            [
                "claude",
                "--model", model_id,
                "--dangerously-skip-permissions",
                prompt
            ],
            cwd=str(project_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL
        )

        stdout, stderr = process.communicate(timeout=300)  # 5 minute timeout

        if process.returncode != 0:
            error_output = stderr.decode()[:1000] if stderr else "No error output"
            logger.error(f"Codex update failed for {task_id}: {error_output}")
            return False

        # Verify codex was updated
        if not codex_path.exists():
            logger.error(f"Codex update failed - docs/codex.md not found after update")
            return False

        new_size = codex_path.stat().st_size
        if new_size < 500:
            logger.warning(f"Codex file suspiciously small ({new_size} bytes) after update")
            return False

        logger.info(f"✅ Living Codex updated for task {task_id}")
        return True

    except subprocess.TimeoutExpired:
        logger.error(f"Codex update timed out for {task_id} (5 min limit)")
        return False
    except Exception as e:
        logger.error(f"Failed to update codex for {task_id}: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_codex_content(project_dir: Path) -> Optional[str]:
    """
    Get current codex content for injection into agent prompts.

    Args:
        project_dir: Project directory

    Returns:
        Codex content string, or None if codex doesn't exist yet
    """
    codex_path = project_dir / "docs" / "codex.md"

    if not codex_path.exists():
        return None

    try:
        return codex_path.read_text()
    except Exception as e:
        logger.error(f"Failed to read codex: {e}")
        return None
