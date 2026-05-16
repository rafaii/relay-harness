"""
Global Project Registry
=======================

Manages global registry of Relay projects.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


def _get_registry_file() -> Path:
    """Get path to global registry file."""
    relay_home = Path.home() / ".relay"
    relay_home.mkdir(exist_ok=True)
    return relay_home / "registry.json"


def _load_registry() -> Dict:
    """Load registry from disk."""
    registry_file = _get_registry_file()
    if not registry_file.exists():
        return {}

    try:
        return json.loads(registry_file.read_text())
    except (json.JSONDecodeError, IOError):
        return {}


def _save_registry(registry: Dict):
    """Save registry to disk."""
    registry_file = _get_registry_file()
    registry_file.write_text(json.dumps(registry, indent=2))


def list_registered_projects() -> Dict:
    """
    List all registered projects.

    Returns:
        Dictionary mapping project name to project info
    """
    return _load_registry()


def register_project(project_name: str, project_dir: Path) -> bool:
    """
    Register a project.

    Args:
        project_name: Unique project name
        project_dir: Project directory path

    Returns:
        True if registered, False if name already exists
    """
    registry = _load_registry()

    if project_name in registry:
        return False

    registry[project_name] = {
        "path": str(project_dir.resolve()),
        "created_at": datetime.now().isoformat(),
        "last_accessed": datetime.now().isoformat()
    }

    _save_registry(registry)
    return True


def unregister_project(project_name: str) -> bool:
    """
    Unregister a project.

    Args:
        project_name: Project name to remove

    Returns:
        True if removed, False if not found
    """
    registry = _load_registry()

    if project_name not in registry:
        return False

    del registry[project_name]
    _save_registry(registry)
    return True


def get_project_path(project_name: str) -> Optional[Path]:
    """
    Get project path by name.

    Args:
        project_name: Project name

    Returns:
        Path to project, or None if not found
    """
    registry = _load_registry()
    if project_name not in registry:
        return None

    return Path(registry[project_name]["path"])


def update_last_accessed(project_name: str):
    """
    Update last accessed time for a project.

    Args:
        project_name: Project name
    """
    registry = _load_registry()

    if project_name in registry:
        registry[project_name]["last_accessed"] = datetime.now().isoformat()
        _save_registry(registry)
