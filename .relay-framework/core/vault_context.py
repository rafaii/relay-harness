"""
Vault Context Manager
=====================

Provides targeted context injection from vault files based on agent role and task.
Replaces monolithic codex injection with domain-specific vault files.
"""

import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


# Role-specific vault file mappings
ROLE_VAULT_FILES = {
    "backend_developer": [
        "planning/system_design.md",
        "planning/security_policy.md",
        "architecture/database-schema.md",
        "backend/api-endpoints.md",
        "backend/services.md",
        "security/authentication.md",
    ],
    "frontend_developer": [
        "planning/system_design.md",
        "planning/ui_standards.md",
        "frontend/pages.md",
        "frontend/components.md",
        "backend/api-endpoints.md",  # Frontend needs to know API contracts
    ],
    "qa": [
        "planning/system_design.md",
        "planning/security_policy.md",
        "backend/api-endpoints.md",
        "frontend/pages.md",
    ],
    "security": [
        "planning/security_policy.md",
        "security/authentication.md",
        "backend/api-endpoints.md",
        "integrations/integrations.md",
    ],
    "database": [
        "planning/system_design.md",
        "architecture/database-schema.md",
        "backend/services.md",
    ],
    "devops": [
        "planning/system_design.md",
        "architecture/tech-stack.md",
        "integrations/integrations.md",
    ],
}

# Keyword-based vault file mappings (for task description analysis)
KEYWORD_VAULT_FILES = {
    "database": ["architecture/database-schema.md"],
    "migration": ["architecture/database-schema.md"],
    "schema": ["architecture/database-schema.md"],
    "api": ["backend/api-endpoints.md"],
    "endpoint": ["backend/api-endpoints.md"],
    "integration": ["integrations/integrations.md"],
    "third-party": ["integrations/integrations.md"],
    "auth": ["security/authentication.md"],
    "login": ["security/authentication.md"],
    "security": ["security/security-policy.md"],
    "ui": ["frontend/ui-standards.md"],
    "component": ["frontend/components.md"],
    "page": ["frontend/pages.md"],
}


class VaultContextManager:
    """Manages vault file retrieval for agent context injection."""

    def __init__(self, project_dir: Path):
        """
        Initialize vault context manager.

        Args:
            project_dir: Project directory containing .relay/vault/
        """
        self.project_dir = Path(project_dir)
        self.vault_dir = self.project_dir / ".relay" / "vault"

        # Check if vault exists, otherwise fall back to legacy
        self.vault_exists = self.vault_dir.exists()

        if not self.vault_exists:
            logger.warning(
                f"Vault not found at {self.vault_dir}. "
                "Using legacy codex summaries. Run 'migrate_to_vault.py' to create vault."
            )

    def get_context_for_agent(self, role: str, task_description: str) -> str:
        """
        Get targeted vault context for an agent.

        Args:
            role: Agent role (backend_developer, frontend_developer, qa, etc.)
            task_description: Task description for keyword analysis

        Returns:
            Combined vault content (targeted sections only)
        """
        if not self.vault_exists:
            logger.error(
                f"Vault not found at {self.vault_dir}. "
                "Run 'python3 .relay-framework/tools/migrate_to_vault.py .' to create vault structure."
            )
            return ""

        # Get base vault files for role
        vault_files = self._get_vault_files_for_role(role)

        # Add keyword-based files from task description
        keyword_files = self._get_vault_files_from_keywords(task_description)
        vault_files.extend(keyword_files)

        # Remove duplicates, preserve order
        vault_files = list(dict.fromkeys(vault_files))

        # Read and combine vault files
        context_parts = []

        for vault_file in vault_files:
            content = self._read_vault_file(vault_file)
            if content:
                context_parts.append(f"## {vault_file}\n\n{content}")

        if not context_parts:
            logger.warning(f"No vault context found for role={role}")
            return ""

        combined = "\n\n---\n\n".join(context_parts)
        token_estimate = len(combined.split())

        logger.info(
            f"Vault context for {role}: {len(vault_files)} files, ~{token_estimate} tokens"
        )

        return combined

    def _get_vault_files_for_role(self, role: str) -> List[str]:
        """Get base vault files for agent role."""
        return ROLE_VAULT_FILES.get(role, [])

    def _get_vault_files_from_keywords(self, text: str) -> List[str]:
        """Extract vault files based on keywords in task description."""
        text_lower = text.lower()
        files = []

        for keyword, vault_files in KEYWORD_VAULT_FILES.items():
            if keyword in text_lower:
                files.extend(vault_files)

        return files

    def _read_vault_file(self, vault_file: str) -> Optional[str]:
        """
        Read a vault file.

        Args:
            vault_file: Relative path from vault root (e.g., "backend/api-endpoints.md")

        Returns:
            File content or None if not found
        """
        path = self.vault_dir / vault_file

        if not path.exists():
            logger.debug(f"Vault file not found: {vault_file}")
            return None

        try:
            content = path.read_text(encoding="utf-8")
            return content
        except Exception as e:
            logger.error(f"Failed to read vault file {vault_file}: {e}")
            return None


    def vault_file_exists(self, vault_file: str) -> bool:
        """Check if a vault file exists."""
        return (self.vault_dir / vault_file).exists()

    def list_all_vault_files(self) -> List[str]:
        """List all markdown files in vault (for debugging)."""
        if not self.vault_exists:
            return []

        files = []
        for md_file in self.vault_dir.rglob("*.md"):
            rel_path = md_file.relative_to(self.vault_dir)
            files.append(str(rel_path))

        return sorted(files)
