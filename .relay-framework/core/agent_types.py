"""
Agent Type Definitions
======================

Central registry of all valid agent types in the Relay Framework.
This ensures consistency across task creation, agent registration, and prompt generation.
"""

# Valid developer agent types (handle development tasks)
DEVELOPER_AGENT_TYPES = [
    "backend_developer",
    "frontend_developer",
    "database_developer",
    "devops_developer",
    "ui_designer",
]

# Valid QA/Security agent types (handle review tasks)
REVIEW_AGENT_TYPES = [
    "qa",
    "security",
]

# All valid agent types
ALL_AGENT_TYPES = DEVELOPER_AGENT_TYPES + REVIEW_AGENT_TYPES


def is_valid_agent_type(agent_type: str) -> bool:
    """
    Check if an agent type is valid.

    Args:
        agent_type: Agent type to validate

    Returns:
        True if valid, False otherwise
    """
    return agent_type in ALL_AGENT_TYPES


def normalize_agent_type(agent_type: str) -> str:
    """
    Normalize agent type to canonical form.

    Handles common mistakes:
    - "devops" → "devops_developer"
    - "database" → "database_developer"
    - "backend" → "backend_developer"
    - "frontend" → "frontend_developer"

    Args:
        agent_type: Agent type to normalize

    Returns:
        Normalized agent type, or original if no normalization needed
    """
    normalization_map = {
        "devops": "devops_developer",
        "database": "database_developer",
        "backend": "backend_developer",
        "frontend": "frontend_developer",
        "ui": "ui_designer",
    }

    return normalization_map.get(agent_type, agent_type)


def get_default_agent_type() -> str:
    """
    Get default agent type for invalid/unknown types.

    Returns:
        Default agent type (backend_developer)
    """
    return "backend_developer"
