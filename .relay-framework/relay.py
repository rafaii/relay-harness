#!/usr/bin/env python3
"""
Relay Framework - Main Entry Point
===================================

Simple, user-friendly entry to multi-agent development system.

Usage:
    relay start              # Start in current directory
    relay start --web        # Launch Web UI instead
    relay resume             # Alias for 'start' (auto-detects)
    relay status             # Show project status
    relay ui                 # Launch Web UI for existing project
    relay init <path>        # Initialize project in specific directory
    relay --help
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add framework directory to Python path
framework_dir = Path(__file__).parent.resolve()
if str(framework_dir) not in sys.path:
    sys.path.insert(0, str(framework_dir))


def has_source_code(project_dir: Path) -> bool:
    """Check if project directory contains actual source code (not just Relay artifacts)."""
    CODE_DIRS = ['src', 'frontend', 'backend', 'client', 'server', 'api', 'web', 'app']
    CODE_EXTENSIONS = ['*.py', '*.[jt]s', '*.tsx', '*.jsx']

    for d in CODE_DIRS:
        code_path = project_dir / d
        if not code_path.exists():
            continue
        for ext in CODE_EXTENSIONS:
            if any(code_path.rglob(ext)):
                return True
    return False


def detect_project_mode(project_dir: Path) -> str:
    """Detect the current project mode for intelligent workflow routing.

    Five-mode detection:
    - 'new': Empty project → full interview (Section 1)
    - 'existing': Has code but no Relay docs → run analyzer first
    - 'resume': Relay docs + incomplete tasks → skip Section 1, resume execution
    - 'add_feature': Relay docs + all tasks done → mini-interview for new feature
    - 'completed': All tasks done, nothing pending

    Returns:
        str: One of 'new', 'existing', 'resume', 'add_feature', 'completed'
    """
    # Check for actual code (not Relay artifacts)
    has_code = has_source_code(project_dir)

    # Check for Relay planning artifacts
    relay_docs_exist = all([
        (project_dir / "docs/system_design.md").exists(),
        (project_dir / "docs/security_policy.md").exists(),
        (project_dir / "docs/ui_standards.md").exists(),
        (project_dir / "docs/master_plan.md").exists()
    ])

    tasks_db_exists = (project_dir / ".relay/tasks.db").exists()

    # Decision matrix
    if not has_code and not relay_docs_exist:
        return "new"
    elif has_code and not relay_docs_exist:
        return "existing"
    elif relay_docs_exist and tasks_db_exists:
        # Check task completion status
        try:
            from core.database import TaskDatabase
            db = TaskDatabase(project_dir)
            stats = db.get_statistics()

            if stats['total'] == 0:
                return "new"  # DB corrupt, restart
            elif stats['completed'] == stats['total']:
                return "add_feature"
            else:
                return "resume"
        except Exception:
            # If DB read fails, check if we have docs
            if relay_docs_exist:
                return "resume"  # Try to resume
            else:
                return "new"
    elif relay_docs_exist and not tasks_db_exists:
        return "resume"  # Planning completed but DB missing
    else:
        return "new"


def main():
    parser = argparse.ArgumentParser(
        description="Relay - Multi-Agent Development Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  relay start                 # Start in current directory
  relay start --web           # Launch Web UI
  relay init ~/my-project     # Initialize specific directory
  relay status                # Show project progress
  relay ui                    # Launch Web UI
        """
    )

    parser.add_argument(
        'command',
        nargs='?',
        default='start',
        choices=['start', 'resume', 'status', 'ui', 'init', 'analyze'],
        help='Command to execute'
    )

    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Project directory (default: current directory)'
    )

    parser.add_argument(
        '--web',
        action='store_true',
        help='Launch Web UI instead of CLI'
    )

    parser.add_argument(
        '--max-agents',
        type=int,
        default=5,
        help='Maximum concurrent agents (default: 5)'
    )

    args = parser.parse_args()

    # Resolve project directory
    project_dir = Path(args.path).resolve()

    if args.command == 'init':
        project_dir.mkdir(parents=True, exist_ok=True)

    if not project_dir.exists():
        print(f"Error: Directory does not exist: {project_dir}")
        sys.exit(1)

    # Detect project mode
    mode = detect_project_mode(project_dir)

    print(f"\n{'='*60}")
    print(f"  Relay Framework")
    print(f"{'='*60}\n")
    print(f"Project: {project_dir}")
    print(f"Mode: {mode.upper().replace('_', ' ')}")
    print()

    # Handle different commands
    if args.command == 'ui' or args.web:
        start_web_ui(project_dir)
        return

    if args.command == 'status':
        show_project_status(project_dir)
        return

    if args.command == 'analyze':
        run_project_analysis(project_dir)
        return

    # Main flow: start/resume with 5-mode routing
    if mode == "new":
        print("No existing project detected. Starting Combined Planning Agent (SECTION 1)...\n")
        success = run_combined_planning_mode(project_dir)
        if not success:
            sys.exit(1)
        print("\n✓ SECTION 1 Complete! Starting SECTION 2 (Execution)...\n")
        # Proceed to execution
        asyncio.run(run_execution_mode(project_dir, args.max_agents))

    elif mode == "existing":
        print("Existing codebase detected without Relay docs.")
        print("Running analyzer to generate planning documents...\n")
        run_project_analysis(project_dir)

    elif mode == "resume":
        print("Resuming execution (SECTION 2)...\n")
        asyncio.run(run_execution_mode(project_dir, args.max_agents))

    elif mode == "add_feature":
        print("All current tasks completed!")
        print("\nTo add new features:")
        print("  1. Run 'relay add \"<feature description>\"' (coming in Phase 2)")
        print("  2. Or manually edit docs/master_plan.md and .relay/tasks.json")

    elif mode == "completed":
        print("✓ All tasks completed!")
        print("\nRun 'relay status' to see final results.")
        print("Run 'relay ui' to launch Web UI.")


def run_combined_planning_mode(project_dir: Path) -> bool:
    """Run combined planning agent (interview + design + security + planning) - SECTION 1."""
    from core.combined_planner import run_combined_planning

    # Create necessary directories
    docs_dir = project_dir / "docs"
    docs_dir.mkdir(exist_ok=True)

    relay_dir = project_dir / ".relay"
    relay_dir.mkdir(exist_ok=True)

    # Initialize project config if it doesn't exist
    config_file = relay_dir / "config.yaml"
    if not config_file.exists():
        from core.config import create_default_config
        create_default_config(project_dir)

    # Run combined planning agent
    success = run_combined_planning(project_dir)

    if not success:
        print("\n✗ Combined planning failed.")
        return False

    print("\n✓ Combined planning completed successfully!")
    return True


async def run_execution_mode(project_dir: Path, max_agents: int):
    """Run SECTION 2 execution loop."""
    from core.orchestrator import RelayOrchestrator

    orchestrator = RelayOrchestrator(project_dir, max_concurrency=max_agents)

    try:
        await orchestrator.run_section_2_execution()
        print("\n✓ Execution complete!")
    except KeyboardInterrupt:
        print("\n\nExecution interrupted by user.")
        print("Run 'relay start' to resume.")
    except Exception as e:
        print(f"\n✗ Execution failed: {e}")
        return False


async def run_resume_mode(project_dir: Path, max_agents: int):
    """Resume existing project."""
    from core.orchestrator import RelayOrchestrator

    orchestrator = RelayOrchestrator(
        project_dir,
        max_concurrency=max_agents
    )

    try:
        await orchestrator.resume()
    except KeyboardInterrupt:
        print("\n\nExecution interrupted by user.")
        print("Run 'relay start' to resume.")
    except Exception as e:
        print(f"\n✗ Execution failed: {e}")
        sys.exit(1)


def show_project_status(project_dir: Path):
    """Display project status."""
    relay_dir = project_dir / ".relay"
    if not relay_dir.exists():
        print("No Relay project found in this directory.")
        print("Run 'relay start' to create a new project.")
        return

    try:
        from core.database import TaskDatabase
        db = TaskDatabase(project_dir)

        # Get statistics
        stats = db.get_statistics()

        if stats['total'] == 0:
            print("No tasks found in database.")
            return

        completion_pct = (stats['completed'] / stats['total'] * 100) if stats['total'] > 0 else 0

        print(f"\nProject Status:")
        print(f"  Total Tasks: {stats['total']}")
        print(f"  Completed: {stats['completed']}")
        print(f"  In Development: {stats.get('in_development', 0)}")
        print(f"  In QA: {stats.get('in_qa', 0)}")
        print(f"  In Security: {stats.get('in_security', 0)}")
        print(f"  To Do: {stats.get('todo', 0)}")
        print(f"  Progress: {completion_pct:.1f}%")

        # Show phases
        tasks_by_phase = db.get_tasks_grouped_by_phase()

        if tasks_by_phase:
            print(f"\nPhase Breakdown:")
            for phase, tasks in tasks_by_phase.items():
                total = len(tasks)
                completed = sum(1 for t in tasks if t.status == 'done')
                phase_pct = (completed / total * 100) if total > 0 else 0
                print(f"  {phase}: {completed}/{total} ({phase_pct:.0f}%)")

        # Show recent activity
        recent = db.get_recent_activity(limit=5)
        if recent:
            print(f"\nRecent Activity:")
            for log in recent:
                print(f"  - {log.agent_name} ({log.agent_type}): {log.action} on {log.task_id}")

        # Check if task_status.md exists
        status_file = project_dir / "docs/task_status.md"
        if status_file.exists():
            print(f"\nDetailed status: {status_file}")

    except Exception as e:
        print(f"Error reading project status: {e}")
        import traceback
        traceback.print_exc()


def start_web_ui(project_dir: Path):
    """Launch Web UI."""
    import os
    import re

    # Auto-register this directory as a project
    project_name = _get_or_create_project_name(project_dir)

    print(f"Starting Web UI for project: {project_name}")
    print(f"Project directory: {project_dir}")
    print("The Web UI will be available at: http://localhost:8888")
    print("\nPress Ctrl+C to stop the server.\n")

    try:
        from core.server.main import app
        import uvicorn

        # Store project directory AND name for the server to use
        os.environ['RELAY_PROJECT_DIR'] = str(project_dir.resolve())
        os.environ['RELAY_PROJECT_NAME'] = project_name

        uvicorn.run(app, host="127.0.0.1", port=8888)
    except KeyboardInterrupt:
        print("\nWeb UI stopped.")
    except Exception as e:
        print(f"Failed to start Web UI: {e}")
        sys.exit(1)


def _get_or_create_project_name(project_dir: Path) -> str:
    """
    Get or create a project name for the given directory.

    If the directory is already registered in the global registry,
    returns its existing name. Otherwise, creates a unique name
    based on the directory name and registers it.

    Args:
        project_dir: Project directory

    Returns:
        Project name (auto-registered if needed)
    """
    from core.registry import list_registered_projects, register_project
    import re

    project_dir = project_dir.resolve()

    # Check if this path is already registered
    projects = list_registered_projects()
    for name, info in projects.items():
        registered_path = Path(info['path']).resolve()
        if registered_path == project_dir:
            # Found existing registration
            print(f"Found registered project: {name}")
            return name

    # Not registered - create a new project name from directory
    base_name = project_dir.name
    if not base_name or base_name == '.':
        base_name = "relay-project"

    # Sanitize name (only alphanumeric, hyphens, underscores)
    base_name = re.sub(r'[^a-zA-Z0-9_-]', '-', base_name)
    base_name = base_name[:45]  # Max 45 chars (leave room for counter)

    # Find unique name
    project_name = base_name
    counter = 1
    existing_names = set(projects.keys())

    while project_name in existing_names:
        project_name = f"{base_name}-{counter}"
        counter += 1

    # Register the project
    try:
        register_project(project_name, project_dir)
        print(f"Auto-registered project: {project_name}")
    except Exception as e:
        print(f"Warning: Could not register project: {e}")
        # Continue anyway - server will still work with the path
        return base_name

    return project_name


def run_project_analysis(project_dir: Path):
    """Analyze existing codebase and generate documentation."""
    from core.analyzer import run_codebase_analysis

    success = run_codebase_analysis(project_dir)

    if success:
        print("\n✓ Analysis complete! Generated:")
        print("  - docs/system_design.md")
        print("  - docs/security_policy.md")
        print("  - docs/ui_standards.md")
        print("  - docs/master_plan.md")
        print("  - tasks.db with approved tasks")
        print("\nNext: Run 'relay start' to begin execution")
    else:
        print("\n✗ Analysis failed. Check logs for details.")
        print("You can:")
        print("  1. Fix issues and run 'relay analyze' again")
        print("  2. Manually create planning documents")
        print("  3. Or run 'relay init' in an empty directory for a new project")


if __name__ == "__main__":
    main()
