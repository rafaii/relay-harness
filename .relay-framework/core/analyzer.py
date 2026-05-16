"""
Codebase Analyzer Agent
=======================

Scans existing codebases and generates architecture documentation
from actual code instead of requiring a manual interview.

Expert fixes incorporated:
- Filtered file tree (excludes node_modules, .git, etc.)
- Smart config extraction (package.json key fields only)
- Pre-inject high-signal source files (schemas, models, routes)
- Generate tasks_draft.json with user approval
- Content size validation (min 800 bytes)
- Capture stderr for error logging
"""

import subprocess
import logging
import json
from pathlib import Path
from .config import get_model_id_for_agent

logger = logging.getLogger(__name__)

ANALYZER_PROMPT = """# Codebase Analyzer Agent

You are analyzing an existing codebase to generate Relay Framework planning documents.

Your task:
1. Examine the codebase structure, files, and patterns
2. Infer the architecture, tech stack, and design decisions
3. Generate 6 documents total:
   - docs/system_design.md (architecture, database schema, API specs)
   - docs/security_policy.md (current security measures + recommendations)
   - docs/ui_standards.md (existing UI patterns + standardization)
   - docs/master_plan.md (refactoring/improvement roadmap)
   - docs/codex.md (Living Codex - what EXISTS right now)
   - .relay/tasks_draft.json (proposed improvement tasks - REQUIRES USER APPROVAL)

**Context:**

Codebase structure (filtered):
{file_tree}

Key configuration files:
{config_files}

High-signal source files (schemas, models, routes):
{key_source_files}

**Instructions:**

1. Read key files to understand:
   - Tech stack (package.json, requirements.txt, etc.)
   - Database schema (models, migrations)
   - API endpoints (route definitions)
   - UI components (component structure, styling)
   - Security implementations (auth, validation)

2. Generate each document with:
   - What EXISTS (current state)
   - What's MISSING (gaps to fill)
   - Recommendations (improvements)

3. Generate tasks_draft.json with improvement/refactoring tasks:
   - Fix security vulnerabilities found
   - Standardize inconsistent patterns
   - Add missing tests
   - Improve error handling
   - Refactor code smells
   - Add missing documentation

   **CRITICAL TASK REQUIREMENTS:**
   - Each task description MUST be 200+ characters
   - MUST reference relevant docs (docs/system_design.md, docs/security_policy.md, docs/ui_standards.md)
   - MUST include acceptance criteria
   - Frontend tasks MUST reference docs/ui_standards.md
   - Security tasks MUST reference docs/security_policy.md

   **JSON Format (tasks_draft.json):**
   ```json
   {{
     "project_name": "Detected from codebase",
     "tasks": [
       {{
         "id": "SEC-001",
         "title": "Short task title",
         "description": "Detailed description (200+ chars) with acceptance criteria and doc references...",
         "phase": "bug_fixes",
         "role": "backend_developer",
         "agent_type": "backend",
         "dependencies": [],
         "priority": 3,
         "complexity": 2
       }}
     ]
   }}
   ```

   **Required fields for each task (DO NOT add any other fields):**
   - id: Unique ID (e.g., SEC-001, REFACTOR-001, TEST-001)
   - title: Short summary (under 80 chars)
   - description: Comprehensive instructions (200+ chars) with acceptance criteria and doc references
   - phase: "bug_fixes", "improvements", "refactoring", "testing", "documentation"
   - role: "backend_developer", "frontend_developer", "qa", "security", "database", "devops"
   - agent_type: "backend", "frontend", "qa", "security", "database", "devops"
   - dependencies: Array of task IDs this depends on (or empty array [])
   - priority: 1-5 (1=highest)
   - complexity: 1-5 (1=simple, 5=complex)

   **IMPORTANT:** Only include these 9 fields. Do NOT add extra fields like "references", "notes", "tags", etc.

4. Write docs/codex.md — the Living Codex documenting ONLY what exists NOW:

   **CRITICAL RULES FOR CODEX:**
   - **Present tense only** - "The API has", "Users can", "The database contains"
   - **Facts only** - What exists NOW (not plans, not TODOs, not future intent)
   - **Derived from actual code** - Build it from what you found in the codebase:
     * Tech stack (from package.json, requirements.txt, Dockerfile)
     * Database tables and columns (from models, migrations, schema files)
     * API endpoints that exist (from route files - method, path, purpose)
     * Frontend pages and shared components (from component/page files)
     * Third-party integrations wired up (from config, .env.example, imports)
     * Security measures in place (from auth middleware, validation)
     * Environment variables required (from .env.example, config files)
     * Test coverage if test files exist

   - **Use standard sections:**
     ## Tech Stack
     ## Database
     ### Tables
     ### Migrations
     ## API Endpoints
     ## Frontend
     ### Pages
     ### Shared Components
     ## Integrations
     ## Security
     ## Environment Variables Required
     ## Test Coverage

   - **Be honest about partial implementations:**
     Good: "Stripe integration: client initialized, payment intent endpoint exists, webhooks not yet handled"
     Bad: "Stripe integration: complete" (when it's not)

   - **No task IDs, no phase names, no "TODO" or "will"**

   This is the source of truth for what is built. After this initial snapshot,
   it will be updated automatically after each completed task.

5. Use Write tool to create all 6 documents

6. Be honest about unknowns (e.g., "Database schema not found in codebase")

**IMPORTANT:**
- The tasks_draft.json file will be shown to the user for approval before creating the tasks database
- Make tasks realistic and actionable based on what you found in the codebase
- After writing all 6 documents, your job is COMPLETE - exit immediately
- DO NOT wait for user input or approval - that happens after you exit

**COMPLETION CHECKLIST:**
Once you have written all 6 files, respond with:
"✅ Analysis complete. All 6 documents written. Exiting."
Then stop immediately.
"""


def run_codebase_analysis(project_dir: Path) -> bool:
    """Analyze existing codebase and generate documentation."""
    project_dir = Path(project_dir)

    print("\n" + "="*80)
    print("🔍 CODEBASE ANALYZER")
    print("="*80)
    print("\nScanning codebase to generate planning documents...\n")

    # Create necessary directories
    (project_dir / "docs").mkdir(exist_ok=True)
    (project_dir / ".relay").mkdir(exist_ok=True)

    # === CHECKPOINT CHECK ===
    # Check if analysis already completed (all 6 documents exist and are valid)
    required_docs = [
        project_dir / "docs/system_design.md",
        project_dir / "docs/security_policy.md",
        project_dir / "docs/ui_standards.md",
        project_dir / "docs/master_plan.md",
        project_dir / "docs/codex.md",
        project_dir / ".relay/tasks_draft.json"
    ]

    MIN_SIZE_BYTES = 800  # ~200 words minimum

    all_docs_exist = all(doc.exists() and doc.stat().st_size >= MIN_SIZE_BYTES for doc in required_docs)

    if all_docs_exist:
        print("✅ Analysis already complete! All 6 documents exist.\n")
        print("Documents found:")
        for doc in required_docs:
            size = doc.stat().st_size
            print(f"  ✓ {doc.relative_to(project_dir)} ({size} bytes)")
        print("\nOptions:")
        print("  1. Review tasks - Show task approval prompt")
        print("  2. Restart - Delete all docs and re-analyze")
        print("  3. Exit - Keep existing docs")
        print()

        choice = input("Your choice (1/2/3): ").strip()

        if choice == "1":
            # Skip to approval flow
            print("\nProceeding to task approval...\n")
            return _run_approval_flow(project_dir)
        elif choice == "2":
            print("\nDeleting existing documents and restarting analysis...\n")
            for doc in required_docs:
                if doc.exists():
                    doc.unlink()
            # Continue to analysis below
        elif choice == "3":
            print("\nKeeping existing documents. Run 'relay start' when ready.")
            return False
        else:
            print("Invalid choice. Exiting.")
            return False

    # 1. Build filtered file tree (Expert fix #1)
    file_tree = _build_file_tree(project_dir)

    # 2. Extract config file contents (Expert fix #2)
    config_files = _extract_config_files(project_dir)

    # 3. Extract key source files (Expert fix #3)
    key_source_files = _extract_key_source_files(project_dir)

    # 4. Build prompt with all context
    prompt = ANALYZER_PROMPT.format(
        file_tree=file_tree,
        config_files=config_files,
        key_source_files=key_source_files
    )

    # 5. Load project config and get model for analyzer
    try:
        from .config import load_project_config
        config = load_project_config(project_dir)
        model_id = get_model_id_for_agent('analyzer', config)
    except Exception as e:
        logger.warning(f"Could not load project config, using default model: {e}")
        model_id = get_model_id_for_agent('analyzer')

    try:
        process = subprocess.Popen(
            [
                "claude",
                "--model", model_id,
                "--dangerously-skip-permissions",
                prompt
            ],
            cwd=str(project_dir),
            stdout=None,  # Stream to terminal for user visibility
            stderr=subprocess.PIPE,  # Capture errors for logging
            stdin=subprocess.DEVNULL  # Explicitly non-interactive
        )

        _, stderr = process.communicate(timeout=1800)  # 30-minute timeout
        returncode = process.returncode

        # Reset terminal to sane mode (Claude CLI leaves it in raw mode)
        # This fixes the issue where input() doesn't accept Enter after Claude exits
        try:
            subprocess.run(["stty", "sane"], stdin=subprocess.DEVNULL, capture_output=True)
        except Exception as e:
            logger.warning(f"Could not reset terminal with 'stty sane': {e}")

        if returncode != 0:
            error_output = stderr.decode()[:2000] if stderr else "No error output"
            logger.error(f"Analyzer failed with exit code {returncode}")
            logger.error(f"Stderr: {error_output}")
            return False

        # Verify documents created + content quality (Expert fix #5)
        required_docs = [
            project_dir / "docs/system_design.md",
            project_dir / "docs/security_policy.md",
            project_dir / "docs/ui_standards.md",
            project_dir / "docs/master_plan.md",
            project_dir / "docs/codex.md",  # Living Codex - initial snapshot from actual code
            project_dir / ".relay/tasks_draft.json"  # Draft tasks for approval
        ]

        MIN_SIZE_BYTES = 800  # ~200 words minimum

        for doc in required_docs:
            if not doc.exists():
                logger.error(f"Missing document: {doc}")
                return False

            size = doc.stat().st_size
            if size < MIN_SIZE_BYTES:
                logger.error(f"Document too short (likely failed): {doc} ({size} bytes, need {MIN_SIZE_BYTES}+)")
                return False

        logger.info("✅ Codebase analysis complete!")

        # === USER APPROVAL PHASE (Expert fix #4) ===
        return _run_approval_flow(project_dir)

    except subprocess.TimeoutExpired:
        logger.error("Analyzer timed out (30-minute limit)")
        return False
    except Exception as e:
        logger.error(f"Analyzer failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def _populate_tasks_database_from_draft(project_dir: Path) -> bool:
    """
    Populate tasks.db from approved tasks_draft.json.
    Similar to _populate_tasks_database in combined_planner.py
    """
    from .database import TaskDatabase

    draft_file = project_dir / ".relay/tasks_draft.json"

    try:
        with open(draft_file, 'r') as f:
            tasks_data = json.load(f)

        db = TaskDatabase(project_dir)

        # Valid Task model fields (filter out any extra fields from analyzer)
        VALID_TASK_FIELDS = {
            'id', 'title', 'description', 'status', 'phase', 'assignee',
            'dependencies', 'priority', 'complexity', 'role', 'agent_type',
            'created_at', 'updated_at'
        }

        for task_data in tasks_data.get('tasks', []):
            # Ensure agent_type is set
            if 'agent_type' not in task_data:
                if 'frontend' in task_data.get('role', '').lower():
                    task_data['agent_type'] = 'frontend'
                else:
                    task_data['agent_type'] = 'backend'

            task_data['status'] = 'todo'

            # Ensure dependencies is a list (not null or missing)
            if 'dependencies' not in task_data or task_data['dependencies'] is None:
                task_data['dependencies'] = []
            elif not isinstance(task_data['dependencies'], list):
                # Convert to list if it's a string or other type
                task_data['dependencies'] = []

            # Filter to only valid fields (remove any extra fields like 'references')
            filtered_task = {k: v for k, v in task_data.items() if k in VALID_TASK_FIELDS}

            db.create_task(filtered_task)

        stats = db.get_statistics()
        logger.info(f"Created {stats['total']} tasks in database")
        return stats['total'] > 0

    except Exception as e:
        logger.error(f"Failed to populate database from draft: {e}")
        return False


def _build_file_tree(project_dir: Path, max_depth: int = 4) -> str:
    """Generate filtered file tree (excludes node_modules, .git, etc.)."""
    IGNORE = {
        "node_modules", ".git", "dist", "build", "__pycache__",
        ".next", "venv", ".venv", "coverage", ".relay-framework",
        "Backup", ".DS_Store", "__MACOSX", ".env"
    }

    lines = []
    try:
        for path in sorted(project_dir.rglob("*")):
            # Skip ignored directories
            if any(part in IGNORE for part in path.parts):
                continue

            if path.is_file():
                rel = path.relative_to(project_dir)
                if len(rel.parts) <= max_depth:
                    lines.append(str(rel))

        return "\n".join(lines) if lines else "No files found (empty directory?)"
    except Exception as e:
        return f"Error building file tree: {e}"


def _extract_config_files(project_dir: Path) -> str:
    """Extract key configuration files smartly."""
    output = []

    # For package.json, extract just meaningful keys (not all 5,000 lines)
    pkg = project_dir / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text())
            summary = {
                k: data[k] for k in ["dependencies", "devDependencies", "scripts", "name", "version"]
                if k in data
            }
            output.append(f"--- package.json (key fields) ---\n{json.dumps(summary, indent=2)}")
        except Exception as e:
            output.append(f"--- package.json (parse error) ---\n{e}")

    # For requirements.txt / pyproject.toml — read fully, they're short
    for fname in ["requirements.txt", "pyproject.toml", "tsconfig.json", ".env.example", "Dockerfile"]:
        path = project_dir / fname
        if path.exists():
            try:
                output.append(f"\n--- {fname} ---\n{path.read_text()}")
            except Exception:
                pass

    return "\n".join(output) if output else "No config files found"


def _extract_key_source_files(project_dir: Path) -> str:
    """Pre-extract high-signal source files (schemas, models, routes)."""
    HIGH_SIGNAL_PATTERNS = [
        "**/schema.prisma",
        "**/models.py",
        "**/models/*.py",
        "**/schema.sql",
        "**/routes/*.py",
        "**/routes/*.ts",
        "**/router/*.ts",
        "**/api/*.py",
        "**/api/*.ts",
        "**/migrations/*.sql",
    ]

    output = []
    seen_files = set()

    for pattern in HIGH_SIGNAL_PATTERNS:
        matches = sorted(project_dir.glob(pattern))[:3]  # Cap at 3 per pattern
        for path in matches:
            if ".git" in str(path) or path in seen_files:
                continue

            seen_files.add(path)
            try:
                content = path.read_text(errors="ignore")[:3000]  # First 3000 chars
                output.append(f"\n--- {path.relative_to(project_dir)} ---\n{content}")
            except Exception:
                pass

    return "\n".join(output) if output else "No high-signal source files found (may need manual review)"


def _validate_task_quality(tasks: list) -> list:
    """
    Validate task description quality.
    Returns list of warning messages (non-blocking).
    """
    warnings = []

    for idx, task_data in enumerate(tasks):
        task_id = task_data.get('id', f'task-{idx}')
        desc = task_data.get('description', '')

        # Short description
        if len(desc) < 200:
            warnings.append(
                f"{task_id}: Short description ({len(desc)} chars, recommend 200+)"
            )

        # Missing doc references
        doc_refs = ['docs/system_design', 'docs/security_policy', 'docs/ui_standards']
        if not any(ref in desc for ref in doc_refs):
            warnings.append(f"{task_id}: No doc references")

        # Missing acceptance criteria
        if 'acceptance' not in desc.lower() and 'criteria' not in desc.lower():
            warnings.append(f"{task_id}: No acceptance criteria")

    return warnings


def _run_approval_flow(project_dir: Path) -> bool:
    """
    Run the approval flow for tasks_draft.json.

    This is extracted as a separate function so it can be called both:
    1. After analyzer completes (normal flow)
    2. When user runs 'relay analyze' again and docs already exist (checkpoint resume)

    Args:
        project_dir: Project directory

    Returns:
        True if tasks approved and database created, False otherwise
    """
    print("\n" + "="*80)
    print("📋 PROPOSED TASKS - REVIEW REQUIRED")
    print("="*80)

    # Load and display draft tasks
    draft_file = project_dir / ".relay/tasks_draft.json"

    if not draft_file.exists():
        logger.error("tasks_draft.json not found. Run 'relay analyze' first.")
        return False

    with open(draft_file, 'r') as f:
        tasks_data = json.load(f)

    # Validate task quality
    validation_warnings = _validate_task_quality(tasks_data.get('tasks', []))

    print(f"\nThe analyzer identified {len(tasks_data.get('tasks', []))} tasks:\n")

    # Show summary of tasks
    for task in tasks_data.get('tasks', []):
        task_id = task.get('id', '???')
        title = task.get('title', 'Untitled')
        phase = task.get('phase', 'unspecified')
        role = task.get('role', 'unspecified')
        complexity = task.get('complexity', '?')

        print(f"  [{task_id}] {title}")
        print(f"      Phase: {phase} | Role: {role} | Complexity: {complexity}")
        print()

    if validation_warnings:
        print("\n⚠️  Task quality warnings:")
        for warning in validation_warnings[:5]:  # Show first 5
            print(f"  - {warning}")
        if len(validation_warnings) > 5:
            print(f"  ... and {len(validation_warnings) - 5} more")
        print()

    print("\nOptions:")
    print("  1. Approve - Create tasks.db and proceed to execution")
    print("  2. Edit - Open tasks_draft.json in editor for manual changes")
    print("  3. Cancel - Keep docs but don't create tasks (manual setup)")
    print()

    while True:
        choice = input("Your choice (1/2/3): ").strip()

        if choice == "1":
            # Create tasks.db from approved draft
            logger.info("Creating tasks database from approved tasks...")
            success = _populate_tasks_database_from_draft(project_dir)
            if success:
                # Rename draft to tasks.json for record-keeping
                (project_dir / ".relay/tasks_draft.json").rename(
                    project_dir / ".relay/tasks.json"
                )
                print("\n✅ Tasks database created!")
                print("\nNext: Run 'relay start' to begin execution")
                return True
            else:
                logger.error("Failed to create tasks database")
                return False

        elif choice == "2":
            # Open in editor
            print("\nOpening tasks_draft.json in editor...")
            print("Edit the tasks, save, and run 'relay analyze' again to review.")
            subprocess.run(["open", str(draft_file)])  # macOS
            return False  # User needs to re-run after editing

        elif choice == "3":
            print("\nDocs created but no tasks database.")
            print("You can manually create .relay/tasks.json and run 'relay start'")
            return False

        else:
            print("Invalid choice. Please enter 1, 2, or 3.")
