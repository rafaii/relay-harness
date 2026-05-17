"""
Vault Update Instructions Generator
====================================

Determines which vault file(s) an agent should update after completing a task.
Generates specific instructions for the agent's system prompt.

Example:
- Task: "Create login page UI"
- Domain: frontend
- Existing file: frontend/pages.md
- Instruction: "After completing task, update .relay/vault/frontend/pages.md with one-line entry for /login page"

Example 2:
- Task: "Add Sentry alerting rules"
- Domain: architecture (monitoring)
- No existing file for alerting
- Instruction: "After completing task, create .relay/vault/architecture/alerting.md + update architecture/index.md"
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Task keywords → vault domain mapping
TASK_DOMAIN_KEYWORDS = {
    "frontend": {
        "keywords": ["page", "component", "ui", "frontend", "react", "vue", "styling", "tailwind", "form", "button", "modal"],
        "domain": "frontend",
        "files": {
            "pages.md": ["page", "route", "view", "screen"],
            "components.md": ["component", "widget", "button", "modal", "form", "input", "card"],
        }
    },
    "backend": {
        "keywords": ["api", "endpoint", "route", "controller", "backend", "service", "business logic"],
        "domain": "backend",
        "files": {
            "api-endpoints.md": ["api", "endpoint", "route", "controller", "GET", "POST", "PUT", "DELETE"],
            "services.md": ["service", "business logic", "class", "method", "function"],
        }
    },
    "architecture": {
        "keywords": ["database", "migration", "schema", "table", "index", "tech stack", "monitoring", "logging", "alerting"],
        "domain": "architecture",
        "files": {
            "database-schema.md": ["database", "migration", "schema", "table", "column", "index", "foreign key"],
            "tech-stack.md": ["library", "package", "dependency", "framework", "tool", "technology"],
        }
    },
    "security": {
        "keywords": ["auth", "authentication", "authorization", "security", "csrf", "cors", "encryption", "mfa", "2fa"],
        "domain": "security",
        "files": {
            "authentication.md": ["auth", "login", "signup", "jwt", "oauth", "mfa", "2fa", "password", "session"],
        }
    },
    "integrations": {
        "keywords": ["integration", "webhook", "third-party", "stripe", "twilio", "whatsapp", "facebook", "api"],
        "domain": "integrations",
        "files": {
            "integrations.md": ["integration", "webhook", "third-party", "stripe", "twilio", "whatsapp", "api"],
        }
    },
}


# Ultra-concise format instructions per file type
FORMAT_INSTRUCTIONS = {
    "frontend/pages.md": """
**Format:** ONE LINE per page
`/route` - What user sees/does, key tech

**Example:**
- `/login` - Email/password form with validation, redirects to dashboard on success
""",
    "frontend/components.md": """
**Format:** ONE LINE per component
`<ComponentName>` - What it renders, key features

**Example:**
- `<Button>` - Primary/secondary/ghost variants, loading state, icon support, accessible
""",
    "backend/api-endpoints.md": """
**Format:** ONE LINE per endpoint
`METHOD /path` - What it does, auth (yes/no), returns what

**Example:**
- `POST /api/auth/login` - Validates email/password, no auth, returns JWT + refresh token or 401
""",
    "backend/services.md": """
**Format:** ONE LINE per service/method
`ClassName.method()` - What it does, key implementation detail

**Example:**
- `AuthService.hashPassword()` - Hashes password with bcrypt (12 rounds), returns hash string
""",
    "architecture/database-schema.md": """
**Format:** ONE LINE per table/change
`table_name` - Columns, relationships, indexes

**Example:**
- `users` - Added email_verified (bool, default false), index on email, foreign key to subscriptions
""",
    "architecture/tech-stack.md": """
**Format:** ONE LINE per technology
Technology - Purpose, version

**Example:**
- Sentry 10.x - Error tracking with email alerts, configured for backend + frontend
""",
    "security/authentication.md": """
**Format:** ONE LINE per mechanism
Mechanism - How it works, tokens/sessions

**Example:**
- MFA/2FA - TOTP-based (speakeasy), 32-char secret encrypted (AES-256-GCM), 30sec window
""",
    "integrations/integrations.md": """
**Format:** ONE LINE per integration
Service - What it does, auth method, key API calls

**Example:**
- Stripe - Payment processing, API key auth, webhook signature validation with stripe.webhooks.constructEvent()
""",
}


def determine_vault_file(task_description: str, project_dir: Path) -> Tuple[Optional[str], bool, str]:
    """
    Determine which vault file should be updated for this task.

    Args:
        task_description: Task description
        project_dir: Project directory

    Returns:
        Tuple of (vault_file_path, file_exists, domain)
        e.g., ("frontend/pages.md", True, "frontend")
    """
    task_lower = task_description.lower()
    vault_dir = project_dir / ".relay" / "vault"

    # Score each domain based on keyword matches
    domain_scores = {}
    for domain_key, config in TASK_DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in config["keywords"] if kw in task_lower)
        if score > 0:
            domain_scores[domain_key] = score

    if not domain_scores:
        logger.info("No vault domain matched for task")
        return None, False, ""

    # Get highest scoring domain
    best_domain_key = max(domain_scores, key=domain_scores.get)
    domain_config = TASK_DOMAIN_KEYWORDS[best_domain_key]
    domain = domain_config["domain"]

    # Find which file in the domain is most relevant
    file_scores = {}
    for filename, keywords in domain_config["files"].items():
        score = sum(1 for kw in keywords if kw in task_lower)
        if score > 0:
            file_scores[filename] = score

    if not file_scores:
        # Domain matched but no specific file - use first file in domain
        first_file = list(domain_config["files"].keys())[0]
        vault_file = f"{domain}/{first_file}"
    else:
        # Get highest scoring file
        best_file = max(file_scores, key=file_scores.get)
        vault_file = f"{domain}/{best_file}"

    # Check if file exists
    file_path = vault_dir / vault_file
    file_exists = file_path.exists()

    logger.info(f"Task vault file: {vault_file} (exists={file_exists}, domain={domain})")

    return vault_file, file_exists, domain


def generate_vault_update_instructions(
    task_description: str,
    project_dir: Path
) -> str:
    """
    Generate vault update instructions for agent system prompt.

    Args:
        task_description: Task description
        project_dir: Project directory

    Returns:
        Instructions text to append to system prompt
    """
    vault_file, file_exists, domain = determine_vault_file(task_description, project_dir)

    if not vault_file:
        return """
## Vault Update (After Task Completion)

No specific vault file identified for this task. If you create something significant:
- Determine the appropriate domain (frontend, backend, architecture, security, integrations)
- Create or update the relevant vault file using ultra-concise one-line format
- See .relay/vault/INDEX.md for domain structure
"""

    format_instructions = FORMAT_INSTRUCTIONS.get(vault_file, "ONE LINE per item")

    if file_exists:
        return f"""
## Vault Update (After Task Completion)

**REQUIRED:** After completing this task, write your vault entry to the task log.

**File that will be updated:** `.relay/vault/{vault_file}` (exists)

**Your responsibility:** At the END of your task log (`.relay/logs/{{task_id}}.md`), add this section:

```markdown
### 📝 Vault Entry

**File:** {vault_file}
**Entry:** [Your ONE LINE entry here following the format below]
```

{format_instructions}

**Important:**
- ONE LINE only - ultra-concise
- Present tense: "Creates", "Returns", "Validates" (not "Will create")
- Include what + how in 5-10 words max

**Example entry for your task:**
`POST /api/auth/login` - Validates email/password, returns JWT + refresh token or 401

**How it works:**
1. You write the entry to your task log
2. Vault writer (automated) reads your entry and appends to `.relay/vault/{vault_file}`
3. Vault stays up-to-date without you directly editing it
"""
    else:
        return f"""
## Vault Update (After Task Completion)

**REQUIRED:** After completing this task, write your vault entry to the task log.

**File that will be created:** `.relay/vault/{vault_file}` (doesn't exist yet)

**Your responsibility:** At the END of your task log (`.relay/logs/{{task_id}}.md`), add this section:

```markdown
### 📝 Vault Entry (New File)

**File:** {vault_file}
**Action:** CREATE_NEW_FILE
**Entry:** [Your ONE LINE entry here following the format below]
**File Description:** [One sentence describing what this file will track]
```

{format_instructions}

**Important:**
- ONE LINE only - ultra-concise
- Present tense: "Creates", "Returns", "Validates"
- Include what + how in 5-10 words max

**Example entry for your task:**
Sentry error rate alert - Triggers when >5 errors/min, sends Slack notification to #alerts

**How it works:**
1. You write the entry + file description to your task log
2. Vault writer (automated) creates `.relay/vault/{vault_file}` with proper header
3. Vault writer updates `.relay/vault/{domain}/index.md` to reference new file
4. You don't directly edit vault files - the system handles it
"""


def get_vault_update_section(task_description: str, project_dir: Path) -> str:
    """
    Get the vault update section to append to system prompt.

    This is called by executor when spawning agents.

    Args:
        task_description: Task description
        project_dir: Project directory

    Returns:
        Formatted vault update instructions
    """
    try:
        instructions = generate_vault_update_instructions(task_description, project_dir)
        return f"\n\n---\n\n{instructions}\n\n---\n"
    except Exception as e:
        logger.error(f"Failed to generate vault update instructions: {e}")
        return ""
