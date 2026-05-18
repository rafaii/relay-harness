"""
Configuration Management
========================

Handles loading, saving, and managing project configuration files.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import json


# Model ID mappings - maps simple names to full Claude model IDs
MODEL_ID_MAP = {
    'opus': 'claude-opus-4',
    'sonnet': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',
    'haiku': 'claude-3-5-haiku-20241022'
}

# Default model used when no specific model is configured for an agent type
DEFAULT_MODEL = 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'

# Default agent limits (to prevent infinite loops and excessive API usage)
DEFAULT_MAX_AGENT_TURNS = 50  # Maximum conversation turns per agent
DEFAULT_MAX_AGENT_TOKENS = 100000  # Maximum total tokens per agent (input + output)

# Default model configuration for all agent types
DEFAULT_AGENT_MODELS = {
    # SECTION 1: Planning & Governance Agents
    'combined_planner': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',   # Combined planning agent (interview + design + planning)
    'analyzer': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',           # Codebase analyzer for existing projects
    'request_agent': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',      # Request agent for features/bugs/improvements
    'interviewer': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',        # Legacy: Interview agent (kept for backward compatibility)
    'architect': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',          # Legacy: System design and architecture
    'security_architect': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0', # Legacy: Security policy creation
    'ui_designer': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',        # UI design, wireframes, component specs
    'ui_agent': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',           # Legacy: UI/wireframe generation (use ui_designer instead)
    'planner': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',            # Legacy: Master plan and task breakdown

    # SECTION 2: Execution Agents
    'frontend_developer': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0', # Frontend implementation (UI, components, styling)
    'backend_developer': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',  # Backend implementation (API, database, business logic)
    'database': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',           # Database migrations and schema changes
    'devops': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',             # DevOps, CI/CD, deployment, infrastructure
    'qa': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',                 # Testing and QA gate
    'security': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',           # Security scanning and validation gate

    # Other
    'coordinator': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',        # Orchestration (if needed)
}


# Default agent names for consistent identification
DEFAULT_AGENT_NAMES = {
    # Frontend Developers (0-4)
    'frontend_developer': 'Stacey',
    'frontend_developer_1': 'Maya',
    'frontend_developer_2': 'Jordan',
    'frontend_developer_3': 'Casey',
    'frontend_developer_4': 'Riley',

    # Backend Developers (0-4)
    'backend_developer': 'Alex',
    'backend_developer_1': 'Sam',
    'backend_developer_2': 'Taylor',
    'backend_developer_3': 'Morgan',
    'backend_developer_4': 'Cameron',

    # QA (0-4)
    'qa': 'Quinn',
    'qa_1': 'Parker',
    'qa_2': 'Avery',
    'qa_3': 'Dakota',
    'qa_4': 'Skyler',

    # Security (0-4)
    'security': 'Phoenix',
    'security_1': 'Sage',
    'security_2': 'River',
    'security_3': 'Azure',
    'security_4': 'Storm',

    # Database (0-4)
    'database': 'Schema',
    'database_1': 'Migrate',
    'database_2': 'Query',
    'database_3': 'Index',
    'database_4': 'Optimize',

    # UI Designer (0-4)
    'ui_designer': 'Pixel',
    'ui_designer_1': 'Canvas',
    'ui_designer_2': 'Sketch',
    'ui_designer_3': 'Figma',
    'ui_designer_4': 'Adobe',

    # DevOps (0-4)
    'devops': 'Docker',
    'devops_1': 'Jenkins',
    'devops_2': 'Kube',
    'devops_3': 'Terraform',
    'devops_4': 'Ansible',

    # Coordinator
    'coordinator': 'Atlas',

    # Analyzer
    'analyzer': 'Architect',

    # Request Agent
    'request_agent': 'RequestHandler'
}


# Default project paths configuration
# NOTE: Framework is NOT hard-coded - it's determined by the interview agent
DEFAULT_PATHS = {
    'frontend': {
        'path': './frontend',
        'package_manager': None,  # To be determined by interview agent
        'framework': None,        # To be determined by interview agent
        'port': None,             # To be determined by interview agent
        'build_command': None,    # To be determined by interview agent
        'dev_command': None       # To be determined by interview agent
    },
    'backend': {
        'path': './backend',
        'package_manager': None,  # To be determined by interview agent
        'framework': None,        # To be determined by interview agent
        'port': None,             # To be determined by interview agent
        'build_command': None,    # To be determined by interview agent
        'dev_command': None       # To be determined by interview agent
    }
}


def detect_project_paths(project_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Auto-detect frontend and backend directories in EXISTING projects

    NOTE: This function is for analyzing existing codebases, not for making
    framework decisions for new projects. Framework choice should be made by
    the interview agent based on user requirements.

    Args:
        project_dir: Project directory path

    Returns:
        Dictionary with detected paths and frameworks or None if detection fails
    """
    paths = {}

    # Detect frontend
    frontend_candidates = ['frontend', 'client', 'web', 'ui', 'app']
    frontend_info = None

    for candidate in frontend_candidates:
        candidate_path = project_dir / candidate
        if candidate_path.exists() and candidate_path.is_dir():
            package_json = candidate_path / 'package.json'
            if package_json.exists():
                try:
                    with open(package_json, 'r') as f:
                        pkg_data = json.load(f)

                    # Detect framework
                    framework = 'unknown'
                    deps = {**pkg_data.get('dependencies', {}), **pkg_data.get('devDependencies', {})}

                    if 'vite' in deps:
                        framework = 'vite-react' if 'react' in deps else 'vite'
                    elif 'next' in deps:
                        framework = 'nextjs'
                    elif 'react-scripts' in deps:
                        framework = 'create-react-app'
                    elif '@angular/core' in deps:
                        framework = 'angular'
                    elif 'vue' in deps:
                        framework = 'vue'

                    # Get scripts
                    scripts = pkg_data.get('scripts', {})
                    dev_command = 'npm run dev' if 'dev' in scripts else 'npm start'
                    build_command = 'npm run build' if 'build' in scripts else None

                    frontend_info = {
                        'path': f'./{candidate}',
                        'package_manager': 'npm',
                        'framework': framework,
                        'port': 5173 if framework.startswith('vite') else (3000 if framework == 'nextjs' else 8080),
                        'build_command': build_command,
                        'dev_command': dev_command
                    }
                    break
                except (json.JSONDecodeError, IOError):
                    continue

    # Detect backend
    backend_candidates = ['backend', 'server', 'api', 'service']
    backend_info = None

    for candidate in backend_candidates:
        candidate_path = project_dir / candidate
        if candidate_path.exists() and candidate_path.is_dir():
            package_json = candidate_path / 'package.json'

            # Check for Node.js backend
            if package_json.exists():
                try:
                    with open(package_json, 'r') as f:
                        pkg_data = json.load(f)

                    # Detect framework
                    framework = 'unknown'
                    deps = {**pkg_data.get('dependencies', {}), **pkg_data.get('devDependencies', {})}

                    if '@nestjs/core' in deps:
                        framework = 'nestjs'
                    elif 'express' in deps:
                        framework = 'express'
                    elif 'fastify' in deps:
                        framework = 'fastify'
                    elif 'koa' in deps:
                        framework = 'koa'

                    # Get scripts
                    scripts = pkg_data.get('scripts', {})
                    dev_command = None
                    if 'start:dev' in scripts:
                        dev_command = 'npm run start:dev'
                    elif 'dev' in scripts:
                        dev_command = 'npm run dev'
                    elif 'start' in scripts:
                        dev_command = 'npm start'

                    build_command = 'npm run build' if 'build' in scripts else None

                    backend_info = {
                        'path': f'./{candidate}',
                        'package_manager': 'npm',
                        'framework': framework,
                        'port': 3000,
                        'build_command': build_command,
                        'dev_command': dev_command
                    }
                    break
                except (json.JSONDecodeError, IOError):
                    continue

            # Check for Python backend
            elif (candidate_path / 'main.py').exists() or (candidate_path / 'app.py').exists():
                # Detect Python framework
                framework = 'unknown'
                if (candidate_path / 'requirements.txt').exists():
                    try:
                        with open(candidate_path / 'requirements.txt', 'r') as f:
                            reqs = f.read().lower()
                            if 'fastapi' in reqs:
                                framework = 'fastapi'
                            elif 'flask' in reqs:
                                framework = 'flask'
                            elif 'django' in reqs:
                                framework = 'django'
                    except IOError:
                        pass

                backend_info = {
                    'path': f'./{candidate}',
                    'package_manager': 'pip',
                    'framework': framework,
                    'port': 8000 if framework in ['fastapi', 'django'] else 5000,
                    'build_command': None,
                    'dev_command': 'python main.py' if (candidate_path / 'main.py').exists() else 'python app.py'
                }
                break

    # Return detected paths
    if frontend_info:
        paths['frontend'] = frontend_info
    if backend_info:
        paths['backend'] = backend_info

    return paths if paths else None


def load_config(project_dir: Path) -> Dict[str, Any]:
    """
    Load configuration from .relay/config.yaml

    Args:
        project_dir: Project directory path

    Returns:
        Configuration dictionary

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is malformed
    """
    config_file = project_dir / ".relay" / "config.yaml"

    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")

    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)

    return config


def load_project_config(project_dir: Path) -> Dict[str, Any]:
    """
    Load project configuration from either config.json or config.yaml.

    Supports both JSON and YAML formats for flexibility.
    JSON format is simpler for users, YAML format supports more complex structures.

    Args:
        project_dir: Project directory path

    Returns:
        Configuration dictionary with agent_models, default_model, etc.

    Raises:
        FileNotFoundError: If neither config file exists
    """
    relay_dir = project_dir / ".relay"

    # Try JSON first (simpler format for users)
    json_config = relay_dir / "config.json"
    if json_config.exists():
        with open(json_config, 'r') as f:
            return json.load(f)

    # Fall back to YAML
    yaml_config = relay_dir / "config.yaml"
    if yaml_config.exists():
        with open(yaml_config, 'r') as f:
            return yaml.safe_load(f)

    raise FileNotFoundError(
        f"No config file found. Expected {json_config} or {yaml_config}"
    )


def save_config(project_dir: Path, config: Dict[str, Any]) -> None:
    """
    Save configuration to .relay/config.yaml

    Args:
        project_dir: Project directory path
        config: Configuration dictionary to save
    """
    relay_dir = project_dir / ".relay"
    relay_dir.mkdir(parents=True, exist_ok=True)

    config_file = relay_dir / "config.yaml"

    with open(config_file, 'w') as f:
        yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)


def create_default_config(
    project_dir: Path,
    project_name: Optional[str] = None,
    project_type: str = "web",
    qa_enabled: bool = True,
    security_enabled: bool = True,
    max_agents: int = 5,
    auto_detect_paths: bool = False
) -> Dict[str, Any]:
    """
    Create and save default configuration

    Args:
        project_dir: Project directory path
        project_name: Project name (defaults to directory name)
        project_type: Type of project (web, api, cli, library, mobile)
        qa_enabled: Enable QA gate
        security_enabled: Enable security gate
        max_agents: Maximum concurrent agents
        auto_detect_paths: Auto-detect paths for EXISTING projects (default False for new projects)
                          For new projects, framework choice is made by interview agent

    Returns:
        Created configuration dictionary
    """
    if project_name is None:
        project_name = project_dir.name

    # For existing projects with code already present, detect their structure
    # For new projects, use minimal defaults - interview agent will populate
    if auto_detect_paths:
        detected_paths = detect_project_paths(project_dir)
        paths = detected_paths if detected_paths else DEFAULT_PATHS.copy()
    else:
        # New project: minimal paths config, interview agent decides framework
        paths = DEFAULT_PATHS.copy()

    config = {
        'project': {
            'name': project_name,
            'type': project_type,
            'created_at': datetime.now().isoformat()
        },

        'paths': paths,

        'gates': {
            'qa_enabled': qa_enabled,
            'security_enabled': security_enabled
        },

        'agents': {
            'max_concurrent': max_agents,

            'models': DEFAULT_AGENT_MODELS.copy(),

            'names': DEFAULT_AGENT_NAMES.copy()
        },

        'status_flow': {
            'states': [
                'todo',
                'in_development',
                'ready_for_qa',
                'in_qa',
                'qa_failed',
                'ready_for_security',
                'in_security',
                'security_failed',
                'done'
            ]
        }
    }

    save_config(project_dir, config)
    return config


def get_agent_name(agent_id: str, config: Optional[Dict[str, Any]] = None) -> str:
    """
    Get human-friendly name for agent ID

    Args:
        agent_id: Agent identifier (e.g., "developer_1", "qa")
        config: Optional config dict (uses defaults if not provided)

    Returns:
        Human-friendly agent name (e.g., "Maya", "Riley")
    """
    if config and 'agents' in config and 'names' in config['agents']:
        names = config['agents']['names']
        return names.get(agent_id, agent_id)

    return DEFAULT_AGENT_NAMES.get(agent_id, agent_id)


def get_model_for_agent(agent_type: str, config: Optional[Dict[str, Any]] = None) -> str:
    """
    Get the model name for a specific agent type

    Args:
        agent_type: Agent type (e.g., "interviewer", "developer", "qa")
        config: Optional config dict (uses defaults if not provided)

    Returns:
        Model name (e.g., "sonnet", "opus", "haiku")
    """
    # Try to get from config first
    if config and 'agents' in config and 'models' in config['agents']:
        models = config['agents']['models']
        if agent_type in models:
            return models[agent_type]

    # Fall back to default agent models
    if agent_type in DEFAULT_AGENT_MODELS:
        return DEFAULT_AGENT_MODELS[agent_type]

    # Ultimate fallback to default model
    return DEFAULT_MODEL


def get_model_id_for_agent(agent_type: str, config: Optional[Dict[str, Any]] = None) -> str:
    """
    Get the full Claude model ID for a specific agent type

    Args:
        agent_type: Agent type (e.g., "interviewer", "developer", "qa")
        config: Optional config dict (uses defaults if not provided)

    Returns:
        Full Claude model ID (e.g., "us.anthropic.claude-sonnet-4-5-20250929-v1:0")

    Example:
        >>> get_model_id_for_agent("interviewer")
        'us.anthropic.claude-sonnet-4-5-20250929-v1:0'

        >>> get_model_id_for_agent("qa")
        'claude-3-5-haiku-20241022'
    """
    model_name = get_model_for_agent(agent_type, config)

    # If it's already a full model ID (contains dots or hyphens), return as-is
    if '.' in model_name or '-' in model_name:
        return model_name

    # Otherwise, map it to full model ID
    return MODEL_ID_MAP.get(model_name, MODEL_ID_MAP[DEFAULT_MODEL])


def get_agent_limits(project_dir: Path, config: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """
    Get agent execution limits (max turns, max tokens) from config or defaults.

    Args:
        project_dir: Project directory path
        config: Optional pre-loaded configuration

    Returns:
        Dictionary with 'max_turns' and 'max_tokens' keys
    """
    if config is None:
        try:
            config = load_project_config(project_dir)
        except FileNotFoundError:
            # No config file, use defaults
            config = {}

    # Get limits from config or use defaults
    agents_config = config.get('agents', {})
    limits = agents_config.get('limits', {})

    return {
        'max_turns': limits.get('max_turns', DEFAULT_MAX_AGENT_TURNS),
        'max_tokens': limits.get('max_tokens', DEFAULT_MAX_AGENT_TOKENS),
    }


def validate_config(config: Dict[str, Any]) -> bool:
    """
    Validate configuration structure

    Args:
        config: Configuration dictionary to validate

    Returns:
        True if valid, False otherwise
    """
    required_keys = ['project', 'gates', 'agents', 'status_flow']

    # Check top-level keys
    for key in required_keys:
        if key not in config:
            return False

    # Check project section
    if 'name' not in config['project'] or 'type' not in config['project']:
        return False

    # Check gates section
    if 'qa_enabled' not in config['gates'] or 'security_enabled' not in config['gates']:
        return False

    # Check agents section
    if 'max_concurrent' not in config['agents']:
        return False

    if 'names' not in config['agents']:
        return False

    # Check status flow
    if 'states' not in config['status_flow']:
        return False

    # Check paths section (optional, but must be valid if present)
    if 'paths' in config:
        paths = config['paths']
        if not isinstance(paths, dict):
            return False

        # Validate each path configuration
        for path_type, path_config in paths.items():
            if not isinstance(path_config, dict):
                return False

            # Required fields in path config
            if 'path' not in path_config:
                return False

            # Optional but recommended fields
            # (package_manager, framework, port, build_command, dev_command)
            # These are not required for validation to pass

    return True


def update_config(project_dir: Path, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update specific config values

    Args:
        project_dir: Project directory path
        updates: Dictionary of updates (supports nested keys with dots)

    Returns:
        Updated configuration

    Example:
        update_config(project_dir, {
            'agents.max_concurrent': 10,
            'gates.qa_enabled': False
        })
    """
    config = load_config(project_dir)

    for key, value in updates.items():
        keys = key.split('.')
        current = config

        # Navigate to nested key
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        # Set value
        current[keys[-1]] = value

    save_config(project_dir, config)
    return config


def get_frontend_path(project_dir: Path, config: Optional[Dict[str, Any]] = None) -> Optional[Path]:
    """
    Get the frontend directory path

    Args:
        project_dir: Project directory path
        config: Optional config dict (will load if not provided)

    Returns:
        Absolute path to frontend directory or None if not configured
    """
    if config is None:
        try:
            config = load_config(project_dir)
        except FileNotFoundError:
            return None

    if 'paths' in config and 'frontend' in config['paths']:
        frontend_path = config['paths']['frontend']['path']
        # Convert relative path to absolute
        if frontend_path.startswith('./'):
            return project_dir / frontend_path[2:]
        elif frontend_path.startswith('/'):
            return Path(frontend_path)
        else:
            return project_dir / frontend_path

    return None


def get_backend_path(project_dir: Path, config: Optional[Dict[str, Any]] = None) -> Optional[Path]:
    """
    Get the backend directory path

    Args:
        project_dir: Project directory path
        config: Optional config dict (will load if not provided)

    Returns:
        Absolute path to backend directory or None if not configured
    """
    if config is None:
        try:
            config = load_config(project_dir)
        except FileNotFoundError:
            return None

    if 'paths' in config and 'backend' in config['paths']:
        backend_path = config['paths']['backend']['path']
        # Convert relative path to absolute
        if backend_path.startswith('./'):
            return project_dir / backend_path[2:]
        elif backend_path.startswith('/'):
            return Path(backend_path)
        else:
            return project_dir / backend_path

    return None


def get_path_info(project_dir: Path, path_type: str, config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Get full path configuration information

    Args:
        project_dir: Project directory path
        path_type: Type of path ('frontend' or 'backend')
        config: Optional config dict (will load if not provided)

    Returns:
        Path configuration dictionary or None if not configured
    """
    if config is None:
        try:
            config = load_config(project_dir)
        except FileNotFoundError:
            return None

    if 'paths' in config and path_type in config['paths']:
        return config['paths'][path_type]

    return None


def list_configured_paths(project_dir: Path, config: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    List all configured path types in the project

    Args:
        project_dir: Project directory path
        config: Optional config dict (will load if not provided)

    Returns:
        List of configured path types (e.g., ['frontend', 'backend'])
    """
    if config is None:
        try:
            config = load_config(project_dir)
        except FileNotFoundError:
            return []

    if 'paths' in config:
        return list(config['paths'].keys())

    return []


def validate_paths(project_dir: Path, config: Optional[Dict[str, Any]] = None) -> Dict[str, bool]:
    """
    Validate that all configured paths actually exist

    Args:
        project_dir: Project directory path
        config: Optional config dict (will load if not provided)

    Returns:
        Dictionary mapping path types to existence status
    """
    if config is None:
        try:
            config = load_config(project_dir)
        except FileNotFoundError:
            return {}

    results = {}

    if 'paths' in config:
        for path_type, path_config in config['paths'].items():
            path_str = path_config.get('path', '')
            if path_str.startswith('./'):
                full_path = project_dir / path_str[2:]
            elif path_str.startswith('/'):
                full_path = Path(path_str)
            else:
                full_path = project_dir / path_str

            results[path_type] = full_path.exists() and full_path.is_dir()

    return results


def update_path_config(
    project_dir: Path,
    path_type: str,
    framework: Optional[str] = None,
    package_manager: Optional[str] = None,
    port: Optional[int] = None,
    build_command: Optional[str] = None,
    dev_command: Optional[str] = None,
    path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update path configuration with interview agent decisions

    This function should be called by the interview agent after gathering
    requirements and making framework decisions.

    Args:
        project_dir: Project directory path
        path_type: Type of path to update ('frontend' or 'backend')
        framework: Framework choice (e.g., 'react', 'vue', 'nestjs', 'fastapi')
        package_manager: Package manager (e.g., 'npm', 'yarn', 'pip')
        port: Port number
        build_command: Build command
        dev_command: Development command
        path: Path to the directory (optional, updates if provided)

    Returns:
        Updated configuration dictionary

    Example:
        # After interview agent decides on React + Vite
        update_path_config(
            project_dir,
            'frontend',
            framework='vite-react',
            package_manager='npm',
            port=5173,
            build_command='npm run build',
            dev_command='npm run dev'
        )
    """
    config = load_config(project_dir)

    # Initialize paths section if it doesn't exist
    if 'paths' not in config:
        config['paths'] = {}

    # Initialize this path type if it doesn't exist
    if path_type not in config['paths']:
        config['paths'][path_type] = {
            'path': f'./{path_type}',
            'package_manager': None,
            'framework': None,
            'port': None,
            'build_command': None,
            'dev_command': None
        }

    # Update only the provided fields
    if path is not None:
        config['paths'][path_type]['path'] = path
    if framework is not None:
        config['paths'][path_type]['framework'] = framework
    if package_manager is not None:
        config['paths'][path_type]['package_manager'] = package_manager
    if port is not None:
        config['paths'][path_type]['port'] = port
    if build_command is not None:
        config['paths'][path_type]['build_command'] = build_command
    if dev_command is not None:
        config['paths'][path_type]['dev_command'] = dev_command

    save_config(project_dir, config)
    return config
