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

        # Regenerate role-specific summaries after Codex update
        import asyncio
        summary_success = asyncio.run(regenerate_summaries(project_dir))
        if not summary_success:
            logger.warning("Some Codex summaries failed to generate (non-blocking)")

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


# ============================================================================
# CODEX SUMMARY GENERATION (Per-Role Summaries)
# ============================================================================

SUMMARY_PROMPTS = {
    "frontend": """# Codex Summary Generator - Frontend

Read docs/codex.md and create a concise summary for frontend developers.

**Target: Under 400 tokens total**

**Include:**
1. Frontend tech stack (one line per tool/library)
2. List of built shared components (name + path)
3. Page count with note to read full codex for details
4. API base URL pattern
5. Known UI gaps from ui_standards.md section

**Exclude:**
- Backend internals, database schemas, env vars
- Security implementation details
- Integration specifics beyond what frontend uses
- Exhaustive page lists (just counts and categories)

**Format:**
```markdown
## Frontend Stack
[One-line each: React version, build tool, router, state, data fetching, forms, styling, UI libs, testing]

## Shared Components (Built)
- ComponentName (path) - brief purpose
[List only what EXISTS, not what's planned]

## Pages (count)
X pages across [categories]. Full list: read docs/codex.md#frontend-pages

## API Base URL
/api — see docs/codex.md#api-endpoints for full list

## Known UI Gaps
- [Brief bullet points from ui_standards.md]
```

Use Write tool to save to `.relay/codex_summary_frontend.md`
""",

    "backend": """# Codex Summary Generator - Backend

Read docs/codex.md and create a concise summary for backend developers.

**Target: Under 400 tokens total**

**Include:**
1. Backend tech stack (one line per tool)
2. Database table names grouped by domain (NO column details)
3. Existing endpoint count per category with note to read full codex
4. Auth pattern summary (JWT type, expiry, bcrypt cost)

**Exclude:**
- Frontend pages, UI components
- Full env var lists (just critical patterns)
- Voice gateway implementation details
- Column-by-column schema details

**Format:**
```markdown
## Backend Stack
[One-line each: framework, ORM, database, cache, queue, auth, logging, monitoring]

## Database (X tables)
Core: [table names]
CRM: [table names]
Agents: [table names]
Full schemas: read docs/codex.md#database

## API (existing endpoints — do not duplicate)
Auth: X endpoints | Businesses: X | CRM: X | Inbox: X
[More categories...]
Full list: read docs/codex.md#api-endpoints

## Auth Pattern
JWT [type], [access expiry] / [refresh expiry], bcrypt cost [N]
Guards: [list guard names]
```

Use Write tool to save to `.relay/codex_summary_backend.md`
""",

    "qa": """# Codex Summary Generator - QA

Read docs/codex.md and create a concise summary for QA engineers.

**Target: Under 300 tokens total**

**Include:**
1. Existing test files and test commands
2. Known gaps (missing tests, coverage issues)
3. API endpoint count per domain (for test coverage awareness)
4. Critical user flows (if documented)

**Exclude:**
- Implementation details (tech stack internals)
- Database schemas
- Environment variables

**Format:**
```markdown
## Test Coverage
[List existing test files and commands]
Coverage: [X%] or "Not tracked"

## Known Gaps
- [Missing test areas from codex]

## API Endpoints (X total)
[Category: count] — test coverage: [status]

## Critical Flows
[If documented, list main user journeys]
```

Use Write tool to save to `.relay/codex_summary_qa.md`
""",

    "security": """# Codex Summary Generator - Security

Read docs/codex.md and create a concise summary for security auditors.

**Target: Under 300 tokens total**

**Include:**
1. Auth mechanisms (JWT, OAuth, MFA)
2. Encryption in use (what and where)
3. Known security gaps from codex
4. Webhook verification status per integration

**Exclude:**
- Frontend pages, UI components
- General tech stack (unless security-relevant)
- Business logic implementation details

**Format:**
```markdown
## Auth Mechanisms
JWT: [type, expiry]
OAuth: [providers]
MFA: [status, method]
Password: [hash algo, cost]

## Encryption
- [What is encrypted and how]

## Known Security Gaps
- [List from docs/security_policy.md or codex]

## Webhook Verification
- WhatsApp: [enabled/disabled]
- Facebook: [enabled/disabled]
- Stripe: [enabled/disabled]
[etc.]
```

Use Write tool to save to `.relay/codex_summary_security.md`
""",

    "database": """# Codex Summary Generator - Database

Read docs/codex.md and create a concise summary for database specialists.

**Target: Under 300 tokens total**

**Include:**
1. Database tech (PostgreSQL version, connection pooling)
2. Table list with domain grouping (NO column details)
3. Migration framework in use
4. Backup/replication status

**Format:**
```markdown
## Database
PostgreSQL [version]
ORM: [name + version]
Migration tool: [tool name]

## Tables ([count] total)
Core: [names]
CRM: [names]
Agents: [names]
Full schemas: read docs/codex.md#database

## Known Issues
- [Any DB-related gaps from codex]
```

Use Write tool to save to `.relay/codex_summary_database.md`
""",

    "devops": """# Codex Summary Generator - DevOps

Read docs/codex.md and create a concise summary for DevOps engineers.

**Target: Under 300 tokens total**

**Include:**
1. Infrastructure components (Docker, NGINX, VPS details)
2. Services and ports
3. Environment variable patterns (not full list)
4. Deployment/CI status

**Format:**
```markdown
## Infrastructure
[List containers, proxy, hosting]

## Services & Ports
Backend: [port]
Frontend: [port]
Voice Gateway: [port]

## Environment Variables
[Groups: Database, Redis, Auth, Integrations, etc.]
Full list: read docs/codex.md#environment-variables

## Deployment
[Docker Compose version, CI/CD status, SSL status]
```

Use Write tool to save to `.relay/codex_summary_devops.md`
"""
}


async def regenerate_summaries(project_dir: Path) -> bool:
    """
    Regenerate role-specific Codex summaries after Codex update.

    Called automatically after update_codex() succeeds.

    Args:
        project_dir: Project directory

    Returns:
        True if all summaries generated successfully
    """
    from .config import get_model_id_for_agent, load_project_config

    # Get model for codex writer
    try:
        config = load_project_config(project_dir)
        model_id = get_model_id_for_agent('codex_writer', config)
    except Exception:
        model_id = 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'

    logger.info("Regenerating Codex summaries for all roles...")

    success_count = 0
    for role, prompt in SUMMARY_PROMPTS.items():
        try:
            logger.info(f"Generating Codex summary for {role}...")

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

            stdout, stderr = process.communicate(timeout=120)  # 2 min per summary

            if process.returncode == 0:
                # Verify summary was created
                summary_path = project_dir / ".relay" / f"codex_summary_{role}.md"
                if summary_path.exists() and summary_path.stat().st_size > 100:
                    logger.info(f"✓ Generated codex_summary_{role}.md")
                    success_count += 1
                else:
                    logger.warning(f"✗ Summary for {role} not created or too small")
            else:
                error_output = stderr.decode()[:500] if stderr else "No error"
                logger.warning(f"✗ Summary generation failed for {role}: {error_output}")

        except subprocess.TimeoutExpired:
            logger.warning(f"✗ Summary generation timed out for {role}")
        except Exception as e:
            logger.warning(f"✗ Failed to generate summary for {role}: {e}")

    logger.info(f"Codex summary generation complete: {success_count}/{len(SUMMARY_PROMPTS)} succeeded")
    return success_count == len(SUMMARY_PROMPTS)
