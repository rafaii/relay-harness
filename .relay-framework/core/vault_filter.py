"""
Vault Content Filter
====================

Extracts only relevant sections from vault files based on task keywords.
Reduces context injection from 1000+ lines to 10-100 lines.

Example:
- Task: "Set up Sentry alerting"
- Keywords: sentry, monitoring, logging, alerting
- Extracted: Only Sentry sections from tech-stack.md + security logging section
- Result: ~50 lines instead of 1000+
"""

import re
import logging
from typing import List, Dict, Set
from pathlib import Path

logger = logging.getLogger(__name__)


# Task type → relevant keywords mapping
TASK_TYPE_KEYWORDS = {
    "monitoring": ["sentry", "logging", "winston", "prometheus", "metrics", "alerting", "monitoring", "error tracking"],
    "authentication": ["auth", "login", "signup", "jwt", "oauth", "mfa", "2fa", "password", "session", "token"],
    "database": ["database", "migration", "schema", "table", "column", "index", "query", "sql", "postgres", "typeorm"],
    "api": ["api", "endpoint", "route", "controller", "request", "response", "rest", "graphql"],
    "integration": ["integration", "webhook", "third-party", "api", "stripe", "twilio", "whatsapp", "facebook"],
    "security": ["security", "csrf", "cors", "xss", "injection", "encryption", "vulnerability", "owasp"],
    "frontend": ["component", "page", "ui", "react", "vue", "styling", "tailwind", "css"],
    "testing": ["test", "jest", "playwright", "e2e", "unit", "integration test", "coverage"],
    "deployment": ["deploy", "docker", "ci/cd", "github actions", "build", "production"],
}


# Vault file → section patterns (regex to identify section boundaries)
VAULT_FILE_SECTIONS = {
    "architecture/tech-stack.md": {
        "patterns": [r"^##\s+(.+)$", r"^###\s+(.+)$"],  # ## and ### headers
        "keywords_map": {
            "sentry": ["Error Tracking", "Monitoring"],
            "logging": ["Logging", "Winston"],
            "database": ["PostgreSQL", "Database"],
            "redis": ["Redis", "Cache"],
            "docker": ["Docker", "Container"],
        }
    },
    "planning/system_design.md": {
        "patterns": [r"^##\s+\d+\.\s+(.+)$"],  # ## 1. Tech Stack
        "keywords_map": {
            "sentry": ["Monitoring"],
            "database": ["Database Schema"],
            "api": ["API Specifications"],
            "architecture": ["Architecture"],
        }
    },
    "planning/security_policy.md": {
        "patterns": [r"^##\s+\d+\.\s+(.+)$"],  # ## 1. Authentication
        "keywords_map": {
            "auth": ["Authentication", "Authorization"],
            "encryption": ["Encryption"],
            "logging": ["Logging", "Monitoring"],
            "csrf": ["CSRF"],
            "security": ["Security"],
        }
    },
    "backend/api-endpoints.md": {
        "patterns": [r"^##\s+(.+)\s+\(/.+\)$"],  # ## Authentication (/auth)
        "keywords_map": {
            "auth": ["Authentication"],
            "business": ["Business Management"],
            "crm": ["CRM"],
            "inbox": ["Inbox"],
            "webhook": ["Webhooks"],
        }
    },
    "backend/services.md": {
        "patterns": [r"^##\s+(.+)$"],  # ## Core Services
        "keywords_map": {
            "auth": ["Auth"],
            "business": ["Business"],
            "contact": ["Contact"],
            "conversation": ["Conversation"],
            "agent": ["Agent", "HITL"],
            "whatsapp": ["WhatsApp"],
            "stripe": ["Stripe"],
            "cache": ["Cache"],
        }
    },
    "architecture/database-schema.md": {
        "patterns": [r"^##\s+(.+)$", r"^###\s+(.+)$"],  # ## and ### headers
        "keywords_map": {
            "user": ["users"],
            "business": ["businesses"],
            "contact": ["contacts", "companies"],
            "conversation": ["conversations", "messages"],
            "deal": ["deals"],
            "agent": ["agent_audit", "hitl_approvals"],
            "integration": ["integration_channels"],
            "subscription": ["subscriptions"],
        }
    },
    "security/authentication.md": {
        "patterns": [r"^##\s+(.+)$"],  # ## JWT Authentication
        "keywords_map": {
            "jwt": ["JWT"],
            "oauth": ["OAuth2"],
            "mfa": ["Multi-Factor", "MFA"],
            "password": ["Password"],
            "admin": ["Admin"],
            "api": ["API Key"],
            "csrf": ["CSRF"],
            "rate": ["Rate Limiting"],
        }
    },
    "frontend/pages.md": {
        "patterns": [r"^##\s+(.+)$"],  # ## Auth Pages
        "keywords_map": {
            "auth": ["Auth Pages"],
            "onboarding": ["Onboarding"],
            "dashboard": ["Dashboard"],
            "crm": ["CRM"],
            "inbox": ["Inbox"],
            "agent": ["Agents"],
            "calendar": ["Calendar"],
            "admin": ["Admin"],
        }
    },
    "frontend/components.md": {
        "patterns": [r"^##\s+(.+)$"],  # ## Form Components
        "keywords_map": {
            "form": ["Form"],
            "button": ["Button"],
            "modal": ["Modal"],
            "table": ["Table"],
            "chart": ["Chart"],
        }
    },
}


def extract_task_keywords(task_description: str) -> Set[str]:
    """
    Extract relevant keywords from task description.

    Args:
        task_description: Task description text

    Returns:
        Set of keywords found in task
    """
    task_lower = task_description.lower()
    keywords = set()

    # Check all known keywords
    for task_type, keyword_list in TASK_TYPE_KEYWORDS.items():
        for keyword in keyword_list:
            if keyword in task_lower:
                keywords.add(keyword)

    return keywords


def filter_vault_file(content: str, filename: str, task_keywords: Set[str]) -> str:
    """
    Filter vault file content to only relevant sections based on task keywords.

    Uses GENERIC filtering for all files:
    - Parses markdown headers (## and ###)
    - Checks if header or section content contains task keywords
    - Returns only matching sections

    Args:
        content: Full vault file content
        filename: Vault file name (e.g., "architecture/tech-stack.md")
        task_keywords: Keywords extracted from task description

    Returns:
        Filtered content with only relevant sections
    """
    if not task_keywords:
        # No task keywords, return first 50 lines
        lines = content.split("\n")
        if len(lines) > 50:
            return "\n".join(lines[:50]) + f"\n\n[... {len(lines) - 50} lines truncated. Read full file if needed: .relay/vault/{filename}]"
        return content

    # Try custom filtering first (for complex patterns)
    if filename in VAULT_FILE_SECTIONS:
        config = VAULT_FILE_SECTIONS[filename]
        keywords_map = config["keywords_map"]

        # Find which sections are relevant
        relevant_section_names = set()
        for keyword in task_keywords:
            if keyword in keywords_map:
                relevant_section_names.update(keywords_map[keyword])

        if relevant_section_names:
            # Extract relevant sections using custom patterns
            return _extract_sections(content, relevant_section_names, config["patterns"])

    # Fall back to GENERIC keyword-based filtering
    return _generic_filter(content, filename, task_keywords)


def _extract_sections(content: str, target_sections: Set[str], section_patterns: List[str]) -> str:
    """
    Extract specific sections from markdown content.

    Args:
        content: Full markdown content
        target_sections: Section names to extract
        section_patterns: Regex patterns for section headers

    Returns:
        Content with only target sections
    """
    lines = content.split("\n")
    result_lines = []
    current_section = None
    in_target_section = False
    section_depth = 0

    for line in lines:
        # Check if this is a section header
        is_header = False
        header_depth = 0
        header_name = None

        for pattern in section_patterns:
            match = re.match(pattern, line)
            if match:
                is_header = True
                header_depth = line.count("#")
                header_name = match.group(1).strip()
                break

        if is_header:
            # Check if this section is a target
            is_target = any(target.lower() in header_name.lower() for target in target_sections)

            # If new section at same or higher level, close previous
            if header_depth <= section_depth:
                in_target_section = is_target
                section_depth = header_depth
                current_section = header_name
            elif is_target:
                # Subsection of current section that's also a target
                in_target_section = True

            if in_target_section:
                result_lines.append(line)
        elif in_target_section:
            result_lines.append(line)

    if not result_lines:
        return f"[No relevant sections found for this task. Read full file if needed: .relay/vault/{content[:50]}...]"

    return "\n".join(result_lines)


def get_filtered_vault_context(vault_files: List[tuple], task_description: str) -> str:
    """
    Get filtered vault context for task.

    Args:
        vault_files: List of (filename, content) tuples
        task_description: Task description for keyword extraction

    Returns:
        Combined filtered vault content
    """
    task_keywords = extract_task_keywords(task_description)

    logger.info(f"Task keywords: {task_keywords}")

    filtered_parts = []
    total_lines_before = 0
    total_lines_after = 0

    for filename, content in vault_files:
        lines_before = len(content.split("\n"))
        total_lines_before += lines_before

        filtered = filter_vault_file(content, filename, task_keywords)
        lines_after = len(filtered.split("\n"))
        total_lines_after += lines_after

        filtered_parts.append(f"## {filename}\n\n{filtered}")

        logger.info(f"Filtered {filename}: {lines_before} → {lines_after} lines ({100 * lines_after // lines_before if lines_before > 0 else 0}%)")

    logger.info(f"Total vault context: {total_lines_before} → {total_lines_after} lines ({100 * total_lines_after // total_lines_before if total_lines_before > 0 else 0}%)")

    return "\n\n---\n\n".join(filtered_parts)


def _generic_filter(content: str, filename: str, task_keywords: Set[str]) -> str:
    """
    Generic keyword-based filtering for ANY markdown file.

    Strategy:
    1. Parse all markdown sections (## and ### headers)
    2. Check if section header OR section content contains task keywords
    3. Return only matching sections

    Args:
        content: Full file content
        filename: File name for logging
        task_keywords: Task keywords to match

    Returns:
        Filtered content with only relevant sections
    """
    lines = content.split("\n")
    sections = []
    current_section = None
    current_section_lines = []

    for line in lines:
        # Check if this is a section header (## or ###)
        if line.startswith("##"):
            # Save previous section
            if current_section:
                sections.append({
                    "header": current_section,
                    "content": "\n".join(current_section_lines)
                })

            # Start new section
            current_section = line
            current_section_lines = [line]
        elif current_section:
            current_section_lines.append(line)

    # Save last section
    if current_section:
        sections.append({
            "header": current_section,
            "content": "\n".join(current_section_lines)
        })

    # Filter sections by keyword match
    relevant_sections = []

    for section in sections:
        header_lower = section["header"].lower()
        content_lower = section["content"].lower()

        # Check if any task keyword appears in header or content
        matches = False
        for keyword in task_keywords:
            if keyword in header_lower or keyword in content_lower:
                matches = True
                break

        if matches:
            relevant_sections.append(section["content"])

    if not relevant_sections:
        # No sections matched - return just headers (table of contents style)
        headers = [s["header"] for s in sections[:10]]  # First 10 headers
        result = "\n".join(headers)
        if len(sections) > 10:
            result += f"\n\n[... {len(sections) - 10} more sections. Read full file if needed: .relay/vault/{filename}]"
        result += f"\n\n**No sections matched task keywords.** Read full file if needed: `.relay/vault/{filename}`"
        return result

    # Return matched sections
    result = "\n\n".join(relevant_sections)
    matched_count = len(relevant_sections)
    total_count = len(sections)

    if matched_count < total_count:
        result += f"\n\n[Showing {matched_count}/{total_count} relevant sections. Read full file for other sections: `.relay/vault/{filename}`]"

    return result
