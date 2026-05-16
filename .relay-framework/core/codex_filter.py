"""
Codex Section Filtering
========================

Extracts only relevant Codex sections for each agent role.
Preserves markdown structure so agents can navigate efficiently.

Target: Inject ~600-1,000 tokens (down from 6,000+ for full codex)
"""

from pathlib import Path
from typing import List, Optional
import re


# Define which Codex sections each role needs
CODEX_SECTIONS_BY_ROLE = {
    "backend_developer": [
        "Tech Stack",
        "Database",
        "API Endpoints",
        "Integrations",
        "Security",
        "Environment Variables Required"
    ],
    "frontend_developer": [
        "Tech Stack",
        "Frontend",
        "API Endpoints",
        "Integrations",
        "Environment Variables Required"
    ],
    "qa": [
        "API Endpoints",
        "Frontend",
        "Test Coverage"
    ],
    "security": [
        "Security",
        "API Endpoints",
        "Integrations",
        "Environment Variables Required"
    ],
    "database": [
        "Tech Stack",
        "Database",
        "API Endpoints"
    ],
    "devops": [
        "Tech Stack",
        "Database",
        "Integrations",
        "Environment Variables Required"
    ],
}


def extract_codex_sections(codex_content: str, role: str) -> str:
    """
    Extract only relevant Codex sections for a given agent role.

    Preserves markdown structure (## headers, lists, tables) so agents can navigate.

    Args:
        codex_content: Full Codex markdown content
        role: Agent role (backend_developer, frontend_developer, etc.)

    Returns:
        Filtered Codex with only relevant sections (preserves markdown formatting)
    """
    if not codex_content:
        return ""

    # Get sections needed for this role
    needed_sections = CODEX_SECTIONS_BY_ROLE.get(role, [])

    if not needed_sections:
        # Unknown role - return full codex (safe fallback)
        return codex_content

    # Split into sections by ## headers
    sections = _parse_codex_sections(codex_content)

    # Filter to only needed sections
    filtered_sections = []

    for section_name, section_content in sections:
        # Check if this section is needed (case-insensitive match)
        if any(needed.lower() in section_name.lower() for needed in needed_sections):
            filtered_sections.append(f"## {section_name}\n{section_content}")

    if not filtered_sections:
        # No matching sections found - return empty (agent can read full file if needed)
        return ""

    return "\n\n".join(filtered_sections)


def _parse_codex_sections(codex_content: str) -> List[tuple]:
    """
    Parse Codex into sections by ## headers.

    Returns:
        List of (section_name, section_content) tuples
    """
    sections = []
    lines = codex_content.split('\n')

    current_section_name = None
    current_section_lines = []

    for line in lines:
        # Check if this is a ## header (but not # or ###)
        if re.match(r'^##\s+[^#]', line):
            # Save previous section
            if current_section_name:
                sections.append((current_section_name, '\n'.join(current_section_lines)))

            # Start new section
            current_section_name = line.replace('##', '').strip()
            current_section_lines = []
        else:
            # Add line to current section
            if current_section_name:
                current_section_lines.append(line)

    # Save last section
    if current_section_name:
        sections.append((current_section_name, '\n'.join(current_section_lines)))

    return sections


def get_filtered_codex_for_role(project_dir: Path, role: str) -> Optional[str]:
    """
    Load Codex and return only sections relevant to the given role.

    Args:
        project_dir: Project directory
        role: Agent role (backend_developer, frontend_developer, etc.)

    Returns:
        Filtered Codex content (with markdown structure preserved)
        Returns None if Codex doesn't exist
    """
    codex_path = project_dir / "docs" / "codex.md"

    if not codex_path.exists():
        return None

    try:
        full_codex = codex_path.read_text()
        filtered_codex = extract_codex_sections(full_codex, role)
        return filtered_codex if filtered_codex else None
    except Exception:
        # If filtering fails, return None (agent can read full file)
        return None
