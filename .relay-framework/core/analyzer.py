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
3. Generate vault structure with domain-specific documentation

**Documents to Create:**

**ALL documentation goes in .relay/vault/ (no separate docs/ folder)**

**Section 1 Planning Docs (.relay/vault/planning/):**
- .relay/vault/planning/system_design.md (overall architecture - ULTRA-CONCISE)
- .relay/vault/planning/security_policy.md (security standards - ULTRA-CONCISE)
- .relay/vault/planning/ui_standards.md (design system - ULTRA-CONCISE)
- .relay/vault/planning/master_plan.md (refactoring/improvement roadmap - FUTURE PLANS)

**Vault Documentation (.relay/vault/):**
- .relay/vault/INDEX.md (main index)
- .relay/vault/CHANGELOG.md (initially empty)
- .relay/vault/architecture/index.md
- .relay/vault/architecture/tech-stack.md (what IS installed/configured)
- .relay/vault/architecture/database-schema.md (tables that EXIST)
- .relay/vault/backend/index.md
- .relay/vault/backend/api-endpoints.md (endpoints that WORK)
- .relay/vault/backend/services.md (services that EXIST)
- .relay/vault/frontend/index.md
- .relay/vault/frontend/pages.md (pages that ARE deployed)
- .relay/vault/frontend/components.md (components that ARE built)
- .relay/vault/integrations/index.md
- .relay/vault/integrations/integrations.md (integrations that WORK)
- .relay/vault/security/index.md
- .relay/vault/security/authentication.md (auth that EXISTS)
- .relay/vault/decisions/index.md
- .relay/vault/decisions/adr-template.md

**Tasks:**
- .relay/tasks_draft.json (proposed improvement tasks - REQUIRES USER APPROVAL)

**Context:**

Codebase structure (filtered):
{file_tree}

Key configuration files:
{config_files}

High-signal source files (schemas, models, routes):
{key_source_files}

**CRITICAL VAULT RULES:**

1. **Vault = CURRENT STATE only** (what IS built, not what WILL be built)
   - Use present tense: "The API has", "Users can", "The database contains"
   - Facts only: Document what EXISTS in the codebase RIGHT NOW
   - NO future plans: "will", "todo", "planned" are FORBIDDEN in vault files

2. **Future plans go in docs/master_plan.md** (NOT in vault)
   - Vault = implementation reality
   - Master plan = improvement roadmap

3. **Exception:** decisions/ can have "Proposed" ADRs (discussing what to build)
   - All other vault folders = facts about what exists

**Instructions:**

1. Read key files to understand:
   - Tech stack (package.json, requirements.txt, etc.)
   - Database schema (models, migrations)
   - API endpoints (route definitions)
   - UI components (component structure, styling)
   - Security implementations (auth, validation)

2. For Section 1 docs (.relay/vault/planning/ folder):

   **CRITICAL: Use ULTRA-CONCISE FORMAT for Section 1 docs**
   - ✅ ONE LINE per item - No paragraphs, no fluff
   - ✅ Bullets and tables - Never prose
   - ✅ What + How in 5-10 words - "JWT auth with RS256, 15min tokens"
   - ✅ Present tense - "Uses", "Requires", "Provides"
   - ❌ No explanations - Just facts, no "This allows users to" or "The purpose is"

   **Good examples:**
   - Frontend: React 18 + Vite, TailwindCSS, React Query for data, React Router
   - Database: PostgreSQL 16 with pgvector extension for embeddings
   - Auth: JWT (RS256), 15min access + 7day refresh tokens, bcrypt(12) for passwords

   **Bad examples (too verbose):**
   - ❌ "The frontend is built using React version 18 which provides improved performance..."

   **Write these files:**
   - .relay/vault/planning/system_design.md (current architecture + gaps)
   - .relay/vault/planning/security_policy.md (current security + recommendations)
   - .relay/vault/planning/ui_standards.md (current design system)
   - .relay/vault/planning/master_plan.md (FUTURE improvements roadmap)

   **What to document:**
   - What EXISTS (current state)
   - What's MISSING (gaps to fill)
   - Recommendations (improvements)

   **Format for system_design.md:**
   ### 1. Tech Stack (one-line bullets)
   - Frontend: [Framework + version], [build tool], [styling], [key libraries]
   - Backend: [Framework + version], [runtime], [key libraries]
   - Database: [Type + version], [ORM], [migration tool]

   ### 2. Architecture (one-line bullets + simple ASCII diagram)
   - Component responsibilities (one line each)
   - Data flow: [A] → [B] → [C]

   ### 3. Database Schema (compact table)
   | Table | Key Fields | Relationships | Indexes |
   |-------|-----------|--------------|---------|

   ### 4. API Specifications (table format)
   | Method | Path | Auth | Purpose |
   |--------|------|------|---------|

   **Format for security_policy.md:**
   ### 1. Auth & Authorization (one-line bullets)
   - Auth method: [type] with [details]
   - Password: [algo](cost), min [N] chars
   - Session: [timeout], [refresh strategy]

   ### 2. Encryption (one-line bullets)
   - At-rest: [algo] for [what]
   - In-transit: [TLS version]

   ### 3. Forbidden Libraries (table)
   | Library | Reason | Use Instead |

   ### 4. Input Validation (one line per threat)
   - SQL Injection: [mitigation]
   - XSS: [mitigation]

   **Format for ui_standards.md:**
   ### 1. Design Language (one-line bullets)
   - Philosophy: [style]
   - Principles: [list]

   ### 2. Color Palette (structured lists with HEX codes)
   - Primary: #HEX
   - Secondary: #HEX
   - Semantic: Success #HEX, Error #HEX

   ### 3. Typography (structured lists)
   - Fonts: [primary], [secondary]
   - Sizes: xs/sm/base/lg/xl with rem values

   ### 4. Components (one-line descriptions)
   - Buttons: [variants, states, sizes]
   - Forms: [input styles, validation, error display]

   **Format for master_plan.md:**
   ### 1. Overview (bullets)
   - Name: [project]
   - Objectives: [3-5 bullets]

   ### 2. Phases (compact format)
   - Phase 1: [name] - [what gets built]

   ### 3. Tasks (ultra-compact)
   - [TASK-001] Title | role | deps | complexity

3. For Vault files (architecture, backend, frontend, etc.):
   - **ONLY what EXISTS** (present tense, facts)
   - Document the ACTUAL implementation
   - If something doesn't exist, don't document it in vault

3. Generate tasks_draft.json with improvement/refactoring tasks:
   - Fix security vulnerabilities found
   - Standardize inconsistent patterns
   - Add missing tests
   - Improve error handling
   - Refactor code smells
   - Add missing documentation

   **CRITICAL TASK REQUIREMENTS:**
   - Each task description MUST be 200+ characters
   - MUST reference relevant docs (.relay/vault/planning/system_design.md, .relay/vault/planning/security_policy.md, .relay/vault/planning/ui_standards.md)
   - MUST include acceptance criteria
   - Frontend tasks MUST reference .relay/vault/planning/ui_standards.md
   - Security tasks MUST reference .relay/vault/planning/security_policy.md

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

4. Write vault files documenting what EXISTS NOW:

   **CRITICAL VAULT RULES:**
   - **Present tense only** - "The API has", "Users can", "The database contains"
   - **Facts only** - What exists NOW (not plans, not TODOs, not future intent)
   - **Each vault file = one domain** - Split by domain, not one big file

   **Vault files to create:**

   **CRITICAL: ULTRA-CONCISE FORMAT**
   - ONE LINE per item (endpoint, page, component, etc.)
   - Format: `thing` - what it does, how (1-2 word implementation detail)
   - NO paragraphs, NO explanations, NO fluff
   - Present tense verbs: Creates, Returns, Validates, Renders

   **Examples of GOOD (concise) entries:**
   ```
   - `POST /api/users` - Creates user with validation, returns 201/user or 400/errors
   - `UserService.hash()` - Hashes password with bcrypt (12 rounds)
   - `/dashboard` - Metrics cards + chart, React Query + Recharts, requires auth
   - `<Button>` - Primary/secondary variants, loading state, accessible
   - Stripe - Payment processing, API key auth, charges.create() + webhooks
   - JWT auth - RS256 signing, 15min access + 7day refresh, httpOnly cookies
   ```

   **Examples of BAD (verbose) entries:**
   ```
   ❌ "The POST /api/users endpoint allows users to create new accounts. It validates
      email format and password strength. Returns 201 on success with user object..."
   ❌ "This button component provides various styling options including primary and
      secondary variants. It supports loading states and accessibility features..."
   ```

   a) `.relay/vault/INDEX.md` - Main navigation
   b) `.relay/vault/CHANGELOG.md` - Initial entry
   c) `.relay/vault/architecture/tech-stack.md` - ONE LINE per tech (Tech - purpose, version)
   d) `.relay/vault/architecture/database-schema.md` - ONE LINE per table (table - columns, indexes)
   e) `.relay/vault/backend/api-endpoints.md` - ONE LINE per endpoint (METHOD /path - what, auth, returns)
   f) `.relay/vault/backend/services.md` - ONE LINE per service/method (Class.method() - what, how)
   g) `.relay/vault/frontend/pages.md` - ONE LINE per page (/route - what user sees, key tech)
   h) `.relay/vault/frontend/components.md` - ONE LINE per component (<Name> - what, features)
   i) `.relay/vault/integrations/integrations.md` - ONE LINE per integration (Service - what, auth, calls)
   j) `.relay/vault/security/authentication.md` - ONE LINE per mechanism (Type - how, tokens/sessions)
   k) Create empty index.md for each domain folder

   This is the source of truth for what is built. After this initial snapshot,
   it will be updated automatically after each completed task.

5. Use Write tool to create all docs + vault files

6. Be honest about unknowns (e.g., "Database schema not found in codebase")

**IMPORTANT:**
- The tasks_draft.json file will be shown to the user for approval before creating the tasks database
- Make tasks realistic and actionable based on what you found in the codebase
- After writing all documents + vault files, your job is COMPLETE - exit immediately
- DO NOT wait for user input or approval - that happens after you exit

**COMPLETION CHECKLIST:**
Once you have written:
- Section 1 planning docs (4 files in .relay/vault/planning/)
- Vault structure (11+ files in .relay/vault/)
- tasks_draft.json (in .relay/)

Respond with:
"✅ Analysis complete. Vault structure + planning docs written. Exiting."
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
    # Check if analysis already completed (Section 1 docs + vault structure exist and are valid)
    # Note: tasks_draft.json gets renamed to tasks.json after approval, so we don't check for it
    permanent_docs = [
        # Section 1 planning docs (now in vault)
        project_dir / ".relay/vault/planning/system_design.md",
        project_dir / ".relay/vault/planning/security_policy.md",
        project_dir / ".relay/vault/planning/ui_standards.md",
        project_dir / ".relay/vault/planning/master_plan.md",
        # Vault structure (check key files)
        project_dir / ".relay/vault/INDEX.md",
        project_dir / ".relay/vault/architecture/tech-stack.md",
        project_dir / ".relay/vault/backend/api-endpoints.md",
    ]

    MIN_SIZE_BYTES = 800  # ~200 words minimum

    all_docs_exist = all(doc.exists() and doc.stat().st_size >= MIN_SIZE_BYTES for doc in permanent_docs)

    # Check if tasks already exist (either draft or approved)
    tasks_draft_exists = (project_dir / ".relay/tasks_draft.json").exists()
    tasks_approved_exists = (project_dir / ".relay/tasks.json").exists()
    tasks_db_exists = (project_dir / ".relay/tasks.db").exists()

    if all_docs_exist and (tasks_draft_exists or tasks_approved_exists or tasks_db_exists):
        print("✅ Analysis already complete! Section 1 docs + vault structure exist.\n")
        print("Documents found:")
        for doc in permanent_docs:
            size = doc.stat().st_size
            print(f"  ✓ {doc.relative_to(project_dir)} ({size} bytes)")

        # Count vault files
        vault_dir = project_dir / ".relay/vault"
        if vault_dir.exists():
            vault_files = list(vault_dir.rglob("*.md"))
            print(f"\n  ✓ Vault: {len(vault_files)} markdown files")

        # Check task status
        if tasks_db_exists:
            print("\n  ✓ tasks.db exists (tasks already approved and loaded)")
        elif tasks_approved_exists:
            print("\n  ✓ tasks.json exists (tasks approved but not loaded)")
        elif tasks_draft_exists:
            print("\n  ✓ tasks_draft.json exists (tasks awaiting approval)")

        print("\nOptions:")
        print("  1. Review tasks - Show task approval prompt (if tasks_draft.json exists)")
        print("  2. Restart - Delete all docs and re-analyze from scratch")
        print("  3. Exit - Keep existing docs")
        print()

        choice = input("Your choice (1/2/3): ").strip()

        if choice == "1":
            # Skip to approval flow (only if draft exists)
            if tasks_draft_exists:
                print("\nProceeding to task approval...\n")
                return _run_approval_flow(project_dir)
            else:
                print("\nNo tasks_draft.json found. Tasks may have already been approved.")
                print("Check .relay/tasks.json or .relay/tasks.db")
                return False
        elif choice == "2":
            print("\nDeleting existing documents and restarting analysis...\n")
            for doc in permanent_docs:
                if doc.exists():
                    doc.unlink()
            # Delete task files too
            for task_file in [".relay/tasks_draft.json", ".relay/tasks.json", ".relay/tasks.db"]:
                task_path = project_dir / task_file
                if task_path.exists():
                    task_path.unlink()
            # Continue to analysis below
        elif choice == "3":
            print("\nKeeping existing documents.")
            if tasks_db_exists:
                print("Run 'relay start' to begin execution.")
            elif tasks_approved_exists or tasks_draft_exists:
                print("Run 'relay analyze' again and choose option 1 to review/approve tasks.")
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

        # Verify Section 1 docs + vault structure created (Expert fix #5)
        required_docs = [
            # Section 1 planning docs
            project_dir / "docs/system_design.md",
            project_dir / "docs/security_policy.md",
            project_dir / "docs/ui_standards.md",
            project_dir / "docs/master_plan.md",
            # Vault structure
            project_dir / ".relay/vault/INDEX.md",
            project_dir / ".relay/vault/CHANGELOG.md",
            project_dir / ".relay/vault/architecture/tech-stack.md",
            project_dir / ".relay/vault/architecture/database-schema.md",
            project_dir / ".relay/vault/backend/api-endpoints.md",
            project_dir / ".relay/vault/frontend/pages.md",
            # Tasks draft
            project_dir / ".relay/tasks_draft.json"
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

        logger.info("✅ Codebase analysis complete! Generated Section 1 docs + vault structure.")

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

    # Ensure project_dir is a Path object
    project_dir = Path(project_dir)

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
            # Ensure role and agent_type are set
            if 'role' not in task_data or not task_data['role']:
                # Infer role from task ID prefix or default to backend
                task_id = task_data.get('id', '')
                if task_id.startswith('FE-') or task_id.startswith('UI-'):
                    task_data['role'] = 'frontend_developer'
                elif task_id.startswith('QA-') or task_id.startswith('TEST-'):
                    task_data['role'] = 'qa'
                elif task_id.startswith('SEC-'):
                    task_data['role'] = 'security'
                elif task_id.startswith('DB-') or task_id.startswith('MIG-'):
                    task_data['role'] = 'database'
                elif task_id.startswith('DEVOPS-') or task_id.startswith('INFRA-'):
                    task_data['role'] = 'devops'
                else:
                    task_data['role'] = 'backend_developer'

            if 'agent_type' not in task_data:
                if 'frontend' in task_data.get('role', '').lower():
                    task_data['agent_type'] = 'frontend'
                elif 'qa' in task_data.get('role', '').lower():
                    task_data['agent_type'] = 'qa'
                elif 'security' in task_data.get('role', '').lower():
                    task_data['agent_type'] = 'security'
                elif 'database' in task_data.get('role', '').lower():
                    task_data['agent_type'] = 'database'
                elif 'devops' in task_data.get('role', '').lower():
                    task_data['agent_type'] = 'devops'
                else:
                    task_data['agent_type'] = 'backend'

            task_data['status'] = 'todo'

            # Ensure phase is set
            if 'phase' not in task_data or not task_data['phase']:
                # Infer phase from task ID or default to improvements
                task_id = task_data.get('id', '')
                if task_id.startswith('SEC-'):
                    task_data['phase'] = 'bug_fixes'
                elif task_id.startswith('TEST-') or task_id.startswith('QA-'):
                    task_data['phase'] = 'testing'
                elif task_id.startswith('REFACTOR-'):
                    task_data['phase'] = 'refactoring'
                elif task_id.startswith('DOC-'):
                    task_data['phase'] = 'documentation'
                else:
                    task_data['phase'] = 'improvements'

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
        doc_refs = ['.relay/vault/planning/system_design', '.relay/vault/planning/security_policy', '.relay/vault/planning/ui_standards']
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
    # Ensure project_dir is a Path object
    project_dir = Path(project_dir)

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
