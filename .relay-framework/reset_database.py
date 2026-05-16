#!/usr/bin/env python3
"""
Database Reset Script
====================

Resets the task database to a clean state:
- Resets all tasks to 'todo' status
- Clears all assignees (frees all agents)
- Removes all entries from task_logs table

Usage:
    python reset_database.py <project_dir>
    python reset_database.py ../new-framework
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.database import TaskDatabase, Task, TaskLog
from sqlalchemy import update, delete


def reset_database(project_dir: Path):
    """
    Reset the database to a clean state.

    Args:
        project_dir: Project directory containing .relay/tasks.db
    """
    project_dir = Path(project_dir).resolve()
    relay_dir = project_dir / ".relay"
    db_file = relay_dir / "tasks.db"

    if not db_file.exists():
        print(f"Error: Database not found at {db_file}")
        print("Make sure you're running this from the correct project directory.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Database Reset")
    print(f"{'='*60}\n")
    print(f"Project: {project_dir}")
    print(f"Database: {db_file}\n")

    # Ask for confirmation
    print("⚠️  WARNING: This will:")
    print("  1. Reset ALL tasks to 'todo' status")
    print("  2. Clear ALL task assignments (set assignee = NULL)")
    print("  3. Delete ALL entries from task_logs table")
    print("\nThis action cannot be undone!\n")

    response = input("Are you sure you want to continue? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("\nAborted.")
        sys.exit(0)

    # Initialize database
    db = TaskDatabase(project_dir)

    print("\nResetting database...")

    with db.get_session() as session:
        # Get statistics before reset
        total_tasks = session.query(Task).count()
        total_logs = session.query(TaskLog).count()

        print(f"\nFound {total_tasks} tasks and {total_logs} log entries")

        # 1. Delete all task logs
        print("\n1. Clearing task_logs table...")
        result = session.execute(delete(TaskLog))
        deleted_logs = result.rowcount
        print(f"   Deleted {deleted_logs} log entries")

        # 2. Reset all tasks to todo and clear assignees
        print("\n2. Resetting tasks to 'todo' and clearing assignees...")
        result = session.execute(
            update(Task).values(
                status='todo',
                assignee=None
            )
        )
        updated_tasks = result.rowcount
        print(f"   Updated {updated_tasks} tasks")

        # Commit changes
        session.commit()

        print(f"\n{'='*60}")
        print("  Reset Complete!")
        print(f"{'='*60}\n")
        print(f"✓ Deleted {deleted_logs} log entries")
        print(f"✓ Reset {updated_tasks} tasks to 'todo'")
        print(f"✓ All agents freed (assignee = NULL)")
        print(f"\nYou can now restart the orchestrator:")
        print(f"  cd {project_dir}")
        print(f"  relay start")


def main():
    parser = argparse.ArgumentParser(
        description="Reset task database to clean state",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python reset_database.py ../new-framework
  python reset_database.py /path/to/project
        """
    )

    parser.add_argument(
        'project_dir',
        help='Project directory containing .relay/tasks.db'
    )

    args = parser.parse_args()

    try:
        reset_database(args.project_dir)
    except KeyboardInterrupt:
        print("\n\nAborted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
