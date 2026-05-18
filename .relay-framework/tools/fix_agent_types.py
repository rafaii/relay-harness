#!/usr/bin/env python3
"""
Fix Invalid Agent Types in Task Database
=========================================

This script validates and corrects agent types in tasks.db to ensure
only valid agent types are used.

Usage:
    python3 fix_agent_types.py /path/to/project

Valid agent types:
- Developer agents: backend_developer, frontend_developer, database_developer,
                    devops_developer, ui_designer
- Review agents: qa, security

Common corrections:
- devops → devops_developer
- database → database_developer
- backend → backend_developer
- frontend → frontend_developer
"""

import sys
import sqlite3
from pathlib import Path

# Add framework to path
framework_dir = Path(__file__).parent.parent
sys.path.insert(0, str(framework_dir))

from core.agent_types import ALL_AGENT_TYPES, normalize_agent_type


def fix_agent_types(project_dir: Path, dry_run: bool = False):
    """
    Fix invalid agent types in task database.

    Args:
        project_dir: Project directory containing .relay/tasks.db
        dry_run: If True, only report issues without making changes
    """
    tasks_db = project_dir / ".relay" / "tasks.db"

    if not tasks_db.exists():
        print(f"❌ Error: No tasks.db found at {tasks_db}")
        return False

    conn = sqlite3.connect(tasks_db)
    cursor = conn.cursor()

    # Check current agent types
    cursor.execute("SELECT DISTINCT role FROM tasks WHERE role IS NOT NULL ORDER BY role")
    current_roles = [row[0] for row in cursor.fetchall()]

    print(f"\n📊 Current agent types in database:")
    for role in current_roles:
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE role = ?", (role,))
        count = cursor.fetchone()[0]
        is_valid = role in ALL_AGENT_TYPES
        status = "✅" if is_valid else "❌"
        print(f"  {status} {role}: {count} tasks")

    # Find tasks with invalid agent types
    cursor.execute("""
        SELECT id, role FROM tasks
        WHERE role IS NOT NULL AND role NOT IN ({})
    """.format(','.join(['?' for _ in ALL_AGENT_TYPES])), ALL_AGENT_TYPES)

    invalid_tasks = cursor.fetchall()

    if not invalid_tasks:
        print(f"\n✅ All agent types are valid!")
        conn.close()
        return True

    print(f"\n🔧 Found {len(invalid_tasks)} tasks with invalid agent types:")

    corrections = {}
    for task_id, role in invalid_tasks:
        normalized = normalize_agent_type(role)
        if normalized not in corrections:
            corrections[normalized] = []
        corrections[normalized].append((task_id, role))

    for new_role, tasks in corrections.items():
        old_role = tasks[0][1]  # Get original role from first task
        task_ids = [t[0] for t in tasks]
        print(f"\n  '{old_role}' → '{new_role}' ({len(tasks)} tasks)")
        print(f"    Task IDs: {', '.join(task_ids[:5])}" + (f" ... and {len(task_ids)-5} more" if len(task_ids) > 5 else ""))

    if dry_run:
        print(f"\n🔍 DRY RUN - No changes made")
        print(f"Run without --dry-run to apply corrections")
        conn.close()
        return True

    # Apply corrections
    print(f"\n✏️  Applying corrections...")

    for new_role, tasks in corrections.items():
        old_role = tasks[0][1]
        task_ids = [t[0] for t in tasks]

        # Update role for all tasks
        cursor.execute(f"""
            UPDATE tasks
            SET role = ?
            WHERE id IN ({','.join(['?' for _ in task_ids])})
        """, [new_role] + task_ids)

        print(f"  ✅ Updated {len(task_ids)} tasks: '{old_role}' → '{new_role}'")

    conn.commit()

    # Verify corrections
    cursor.execute("""
        SELECT COUNT(*) FROM tasks
        WHERE role IS NOT NULL AND role NOT IN ({})
    """.format(','.join(['?' for _ in ALL_AGENT_TYPES])), ALL_AGENT_TYPES)

    remaining_invalid = cursor.fetchone()[0]

    if remaining_invalid > 0:
        print(f"\n⚠️  Warning: {remaining_invalid} tasks still have invalid agent types")
        conn.close()
        return False

    print(f"\n✅ All agent types corrected successfully!")

    # Show final distribution
    print(f"\n📊 Final agent type distribution:")
    cursor.execute("SELECT role, COUNT(*) FROM tasks WHERE role IS NOT NULL GROUP BY role ORDER BY role")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} tasks")

    conn.close()
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 fix_agent_types.py /path/to/project [--dry-run]")
        print("\nExample:")
        print("  python3 fix_agent_types.py /Users/user/my-project")
        print("  python3 fix_agent_types.py /Users/user/my-project --dry-run")
        sys.exit(1)

    project_path = Path(sys.argv[1])
    dry_run = "--dry-run" in sys.argv

    if not project_path.exists():
        print(f"❌ Error: Project directory does not exist: {project_path}")
        sys.exit(1)

    success = fix_agent_types(project_path, dry_run=dry_run)
    sys.exit(0 if success else 1)
