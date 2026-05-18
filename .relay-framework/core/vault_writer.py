"""
Vault Writer
============

Updates vault files when tasks complete.
Replaces monolithic codex writer with targeted vault file updates.

Strategy:
- Determine which vault file(s) to update based on task role/description
- Generate ONLY the new entry (50-200 tokens)
- Append to specific vault file
- Update CHANGELOG.md
- Takes ~10-30 seconds instead of 5 minutes
"""

import asyncio
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


# Map task roles to vault files
ROLE_VAULT_FILE_MAPPING = {
    "backend_developer": ["backend/api-endpoints.md", "backend/services.md"],
    "frontend_developer": ["frontend/pages.md", "frontend/components.md"],
    "database": ["architecture/database-schema.md"],
    "devops": ["architecture/tech-stack.md"],
    "qa": [],  # QA doesn't update vault (only tests)
    "security": [],  # Security doesn't update vault (only reviews)
}

# Keyword-based vault file detection
KEYWORD_VAULT_MAPPING = {
    "database": ["architecture/database-schema.md"],
    "migration": ["architecture/database-schema.md"],
    "schema": ["architecture/database-schema.md"],
    "api": ["backend/api-endpoints.md"],
    "endpoint": ["backend/api-endpoints.md"],
    "integration": ["integrations/integrations.md"],
    "third-party": ["integrations/integrations.md"],
    "component": ["frontend/components.md"],
    "page": ["frontend/pages.md"],
    "authentication": ["security/authentication.md"],
    "auth": ["security/authentication.md"],
}


async def update_vault(project_dir: Path, task_id: str, task_data: dict) -> bool:
    """
    Update vault files after task completion.

    NEW BEHAVIOR: First checks task log for agent-provided vault entry.
    If found, uses that. Otherwise falls back to automated generation.

    Args:
        project_dir: Project directory
        task_id: Task ID (e.g., "BE-001")
        task_data: Task data with title, role, description

    Returns:
        True if update succeeded, False otherwise
    """
    project_dir = Path(project_dir)
    vault_dir = project_dir / ".relay" / "vault"

    # Check if vault exists
    if not vault_dir.exists():
        logger.info(f"Vault doesn't exist yet at {vault_dir}. Skipping vault update for {task_id}.")
        logger.info("Run 'migrate_to_vault.py' to create vault structure.")
        return True  # Not an error, just skip

    # Check if agent provided vault entry in task log
    vault_entry = _extract_vault_entry_from_log(project_dir, task_id)

    if vault_entry:
        logger.info(f"Found agent-provided vault entry for {task_id}")
        return await _apply_vault_entry(project_dir, vault_dir, task_id, vault_entry, task_data)

    # Fall back to automated vault update (old behavior)
    logger.info(f"No agent vault entry found, using automated update for {task_id}")

    # Determine which vault files to update
    vault_files = _determine_vault_files(task_data)

    if not vault_files:
        logger.info(f"No vault files to update for {task_id} (role: {task_data.get('role', '?')})")
        return True  # Not an error, QA/Security tasks don't update vault

    logger.info(f"Updating vault for {task_id}: {vault_files}")

    # Update each vault file
    success = True
    for vault_file in vault_files:
        file_success = await _update_vault_file(
            project_dir, vault_dir, vault_file, task_id, task_data
        )
        if not file_success:
            success = False

    # Update changelog
    if success:
        _update_changelog(vault_dir, task_id, task_data, vault_files)

    return success


def _determine_vault_files(task_data: dict) -> List[str]:
    """
    Determine which vault files to update based on task role and description.

    Args:
        task_data: Task data with role, description

    Returns:
        List of vault file paths (relative to vault root)
    """
    vault_files = []

    # Get base files from role
    role = task_data.get("role", "")
    base_files = ROLE_VAULT_FILE_MAPPING.get(role, [])
    vault_files.extend(base_files)

    # Add keyword-based files from description
    description = (task_data.get("description") or "").lower()
    for keyword, files in KEYWORD_VAULT_MAPPING.items():
        if keyword in description:
            vault_files.extend(files)

    # Remove duplicates, preserve order
    vault_files = list(dict.fromkeys(vault_files))

    return vault_files


async def _update_vault_file(
    project_dir: Path,
    vault_dir: Path,
    vault_file: str,
    task_id: str,
    task_data: dict,
) -> bool:
    """
    Update a specific vault file by generating and appending new entry.

    Args:
        project_dir: Project directory
        vault_dir: Vault directory
        vault_file: Vault file path (relative to vault root)
        task_id: Task ID
        task_data: Task data

    Returns:
        True if successful
    """
    vault_file_path = vault_dir / vault_file

    # Create file if it doesn't exist
    if not vault_file_path.exists():
        vault_file_path.parent.mkdir(parents=True, exist_ok=True)
        vault_file_path.write_text(f"# {vault_file_path.stem.replace('-', ' ').title()}\n\n")
        logger.info(f"Created new vault file: {vault_file}")

    # Read task log to understand what was built
    task_log_path = project_dir / ".relay" / "logs" / f"{task_id}.md"
    task_log = ""
    if task_log_path.exists():
        try:
            task_log = task_log_path.read_text()
            # Limit to last 2000 chars (recent work)
            if len(task_log) > 2000:
                task_log = task_log[-2000:]
        except Exception as e:
            logger.warning(f"Failed to read task log: {e}")

    # Generate new entry using Claude
    prompt = _build_vault_update_prompt(vault_file, task_id, task_data, task_log)

    try:
        # Get model ID for vault writer
        # Try codex_writer first, fall back to backend_developer if not configured
        from core.config import get_model_id_for_agent
        model_id = get_model_id_for_agent("codex_writer")  # Use codex_writer model for vault updates

        # Spawn Claude to generate ONLY the new entry
        process = subprocess.Popen(
            [
                "claude",
                "--model", model_id,
                "--dangerously-skip-permissions",
            ],
            cwd=str(project_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,  # Pass prompt via stdin
        )

        # Wait with timeout (60 seconds for analysis + generation)
        stdout, stderr = await asyncio.wait_for(
            asyncio.to_thread(process.communicate, input=prompt.encode("utf-8")),
            timeout=60.0
        )

        if process.returncode != 0:
            error_msg = stderr.decode()[:500] if stderr else "No error output"
            logger.error(f"Vault update failed for {vault_file}: {error_msg}")
            return False

        # Parse the output (should be bullet points)
        entry = stdout.decode().strip()

        if not entry:
            logger.error(f"Empty vault entry generated for {vault_file}")
            return False

        # Append entry to vault file
        vault_file_content = vault_file_path.read_text()
        if not vault_file_content.endswith("\n"):
            vault_file_content += "\n"
        vault_file_content += f"{entry}\n"
        vault_file_path.write_text(vault_file_content)

        logger.info(f"✅ Vault file updated: {vault_file}")
        return True

    except asyncio.TimeoutError:
        logger.error(f"Vault update timed out for {vault_file} (60s limit)")
        process.kill()
        return False
    except Exception as e:
        logger.error(f"Failed to update vault file {vault_file}: {e}")
        return False


def _build_vault_update_prompt(
    vault_file: str, task_id: str, task_data: dict, task_log: str
) -> str:
    """
    Build prompt for Claude to generate vault entry.

    Args:
        vault_file: Vault file being updated
        task_id: Task ID
        task_data: Task data
        task_log: Task log content

    Returns:
        Prompt string
    """
    # Determine what type of entry to generate based on vault file
    entry_instructions = _get_entry_instructions(vault_file)

    prompt = f"""# Generate Vault Entry

Task completed:
**ID:** {task_id}
**Title:** {task_data.get('title', 'Unknown')}
**Role:** {task_data.get('role', 'Unknown')}

**What was built (from task log):**
{task_log}

{entry_instructions}

**Output ONLY the vault entry (1-3 bullet points). No explanations, no file edits.**

RULES:
1. ULTRA-CONCISE - One line per item
2. Present tense: "Creates", "Returns", "Validates"
3. Format: `thing` - What it does, how it works
4. NO task IDs, NO "will"/"todo", NO paragraphs

Example output:
```
- `POST /api/contacts` - Creates contact with validation, returns 201/contact or 400/errors
- `UserService.findByEmail()` - Queries users table by email with case-insensitive match
```

Output ONLY the bullet points (starting with "- "), nothing else.
"""

    return prompt


def _get_entry_instructions(vault_file: str) -> str:
    """Get file-specific instructions for entry format."""

    instructions = {
        "backend/api-endpoints.md": """
**ONE LINE per endpoint:**
`METHOD /path` - What it does, auth (yes/no), returns what

Example: `POST /api/users` - Creates user with email/password validation, no auth, returns 201/user or 400/errors
""",
        "backend/services.md": """
**ONE LINE per service/method:**
`ClassName.method()` - What it does, key implementation detail

Example: `AuthService.hashPassword()` - Hashes password with bcrypt (12 rounds), returns hash string
""",
        "frontend/pages.md": """
**ONE LINE per page:**
`/route` - What user sees/does, key tech

Example: `/dashboard` - Metrics cards + revenue chart, uses React Query + Recharts, requires auth
""",
        "frontend/components.md": """
**ONE LINE per component:**
`<ComponentName>` - What it renders, key features

Example: `<Button>` - Primary/secondary/ghost variants, loading state, icon support, accessible
""",
        "architecture/database-schema.md": """
**ONE LINE per table/change:**
`table_name` - Columns added/changed, relationships, indexes

Example: `users` - Added email_verified (bool, default false), index on email, foreign key to subscriptions
""",
        "integrations/integrations.md": """
**ONE LINE per integration:**
Service - What it does, auth method, key calls

Example: Stripe - Payment processing, API key auth, `charges.create()` and `webhooks.verify()`
""",
        "architecture/tech-stack.md": """
**ONE LINE per technology:**
Tech - Purpose, version

Example: PostgreSQL 16 - Primary database with pgvector extension for embeddings
""",
        "security/authentication.md": """
**ONE LINE per mechanism:**
Mechanism - How it works, tokens/sessions

Example: JWT auth - RS256 signing, 15min access + 7day refresh tokens, stored in httpOnly cookies
""",
    }

    return instructions.get(vault_file, """
**ONE LINE per item:**
What - How it works, key detail

Be ultra-concise.
""")


def _update_changelog(
    vault_dir: Path, task_id: str, task_data: dict, vault_files: List[str]
):
    """
    Update CHANGELOG.md with entry for this task.

    Args:
        vault_dir: Vault directory
        task_id: Task ID
        task_data: Task data
        vault_files: List of vault files updated
    """
    changelog_path = vault_dir / "CHANGELOG.md"

    if not changelog_path.exists():
        logger.warning(f"CHANGELOG.md not found, skipping changelog update")
        return

    try:
        # Read current changelog
        content = changelog_path.read_text()

        # Find the entries table
        if "## Entries" not in content:
            logger.warning("CHANGELOG.md missing '## Entries' section")
            return

        # Build new entry
        date = datetime.now().strftime("%Y-%m-%d")
        title = task_data.get("title", "Unknown")
        files_str = ", ".join(vault_files)
        description = f"Completed {task_id}: {title}"

        new_entry = f"| {date} | {title} | {files_str} | N/A | {description} |\n"

        # Insert after the header row
        lines = content.split("\n")
        insert_index = None
        for i, line in enumerate(lines):
            if line.startswith("|---"):
                insert_index = i + 1
                break

        if insert_index:
            lines.insert(insert_index, new_entry)
            changelog_path.write_text("\n".join(lines))
            logger.info(f"Updated CHANGELOG.md with {task_id}")
        else:
            logger.warning("Could not find table header in CHANGELOG.md")

    except Exception as e:
        logger.error(f"Failed to update changelog: {e}")


def _extract_vault_entry_from_log(project_dir: Path, task_id: str) -> Optional[dict]:
    """
    Extract vault entry from agent's task log.

    Looks for section: "### 📝 Vault Entry"

    Args:
        project_dir: Project directory
        task_id: Task ID

    Returns:
        Dict with {file, entry, action, description} or None
    """
    log_path = project_dir / ".relay" / "logs" / f"{task_id}.md"

    if not log_path.exists():
        return None

    try:
        content = log_path.read_text()

        # Look for vault entry section
        if "### 📝 Vault Entry" not in content:
            return None

        # Extract the section
        import re
        pattern = r"### 📝 Vault Entry.*?\n(.*?)(?:\n###|\n---|\Z)"
        match = re.search(pattern, content, re.DOTALL)

        if not match:
            return None

        section = match.group(1).strip()

        # Parse fields
        file_match = re.search(r"\*\*File:\*\*\s*(.+)", section)
        entry_match = re.search(r"\*\*Entry:\*\*\s*(.+)", section)
        action_match = re.search(r"\*\*Action:\*\*\s*(.+)", section)
        desc_match = re.search(r"\*\*File Description:\*\*\s*(.+)", section)

        if not file_match or not entry_match:
            logger.warning(f"Incomplete vault entry in {task_id} log")
            return None

        return {
            "file": file_match.group(1).strip(),
            "entry": entry_match.group(1).strip(),
            "action": action_match.group(1).strip() if action_match else "UPDATE",
            "description": desc_match.group(1).strip() if desc_match else None,
        }

    except Exception as e:
        logger.error(f"Failed to extract vault entry from {task_id} log: {e}")
        return None


async def _apply_vault_entry(
    project_dir: Path,
    vault_dir: Path,
    task_id: str,
    vault_entry: dict,
    task_data: dict
) -> bool:
    """
    Apply agent-provided vault entry.

    Args:
        project_dir: Project directory
        vault_dir: Vault directory
        task_id: Task ID
        vault_entry: Dict with file, entry, action, description
        task_data: Task data

    Returns:
        True if successful
    """
    vault_file = vault_entry["file"]
    entry = vault_entry["entry"]
    action = vault_entry.get("action", "UPDATE")

    vault_file_path = vault_dir / vault_file

    try:
        if action == "CREATE_NEW_FILE":
            # Create new vault file
            vault_file_path.parent.mkdir(parents=True, exist_ok=True)

            file_title = vault_file.split("/")[1].replace("-", " ").replace(".md", "").title()
            content = f"""# {file_title}

**Last Updated:** {datetime.now().strftime("%Y-%m-%d")}

## Entries

- {entry}
"""
            vault_file_path.write_text(content)
            logger.info(f"Created new vault file: {vault_file}")

            # Update domain index
            domain = vault_file.split("/")[0]
            index_path = vault_dir / domain / "index.md"

            if index_path.exists():
                index_content = index_path.read_text()
                filename = vault_file.split("/")[1]
                desc = vault_entry.get("description", "Documentation")

                # Add to ## Files section
                new_line = f"- [{filename}]({filename}) - {desc}\n"

                if "## Files" in index_content:
                    # Insert after ## Files line
                    lines = index_content.split("\n")
                    insert_idx = None
                    for i, line in enumerate(lines):
                        if line.startswith("## Files"):
                            insert_idx = i + 2  # Skip ## Files and blank line
                            break

                    if insert_idx:
                        lines.insert(insert_idx, new_line.rstrip())
                        index_path.write_text("\n".join(lines))
                        logger.info(f"Updated {domain}/index.md with new file reference")

        else:
            # Update existing file
            if not vault_file_path.exists():
                logger.warning(f"Vault file {vault_file} doesn't exist, creating it")
                vault_file_path.parent.mkdir(parents=True, exist_ok=True)
                file_title = vault_file.split("/")[1].replace("-", " ").replace(".md", "").title()
                content = f"""# {file_title}

**Last Updated:** {datetime.now().strftime("%Y-%m-%d")}

## Entries

- {entry}
"""
                vault_file_path.write_text(content)
            else:
                # Append entry
                content = vault_file_path.read_text()
                if not content.endswith("\n"):
                    content += "\n"
                content += f"- {entry}\n"
                vault_file_path.write_text(content)

            logger.info(f"Updated vault file: {vault_file}")

        # Update changelog
        _update_changelog(vault_dir, task_id, task_data, [vault_file])

        return True

    except Exception as e:
        logger.error(f"Failed to apply vault entry for {task_id}: {e}")
        return False


def should_update_vault(task_data: dict) -> bool:
    """
    Check if vault should be updated for this task.

    Args:
        task_data: Task data with role

    Returns:
        True if vault should be updated
    """
    role = task_data.get("role", "")

    # QA and Security don't update vault (they only test/review)
    if role in ["qa", "security"]:
        return False

    # Check if there are vault files for this role
    vault_files = _determine_vault_files(task_data)
    return len(vault_files) > 0
