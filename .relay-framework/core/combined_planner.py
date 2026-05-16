"""
Combined Planning Agent for Relay Framework
============================================

Combines interview, architecture, security design, UI/UX design, and planning into ONE Claude CLI session.
This dramatically reduces Section 1 time from 20-40 minutes to 10-15 minutes.

Process:
1. PHASE 1: Interactive interview with user
2. PHASE 2: Generate all planning documents in same session:
   - docs/system_design.md
   - docs/security_policy.md
   - docs/ui_standards.md (NEW in v2.1 - replaces on-demand wireframes)
   - docs/master_plan.md
   - .relay/tasks.json
"""

import subprocess
import logging
import json
from pathlib import Path
from datetime import datetime
from .config import get_model_id_for_agent
from .database import TaskDatabase

logger = logging.getLogger(__name__)


# Checkpointing constants
PLANNING_PROGRESS_KEY = "planning_progress"


def init_planning_state(db: TaskDatabase) -> dict:
    """Initialize planning progress state in database metadata."""
    state = {
        "phase": "starting",
        "started_at": datetime.now().isoformat(),
        "documents": {
            "system_design.md": {"status": "pending", "size": 0},
            "security_policy.md": {"status": "pending", "size": 0},
            "ui_standards.md": {"status": "pending", "size": 0},
            "master_plan.md": {"status": "pending", "size": 0},
            "tasks.json": {"status": "pending", "size": 0}
        },
        "attempts": []
    }
    db.metadata.set_value(PLANNING_PROGRESS_KEY, state)
    return state


def verify_and_checkpoint_documents(project_dir: Path) -> dict:
    """Check each document and update checkpoint incrementally."""
    db = TaskDatabase(project_dir)
    state = db.metadata.get_value(PLANNING_PROGRESS_KEY) or {}

    docs = {
        "system_design.md": project_dir / "docs" / "system_design.md",
        "security_policy.md": project_dir / "docs" / "security_policy.md",
        "ui_standards.md": project_dir / "docs" / "ui_standards.md",
        "master_plan.md": project_dir / "docs" / "master_plan.md",
        "tasks.json": project_dir / ".relay" / "tasks.json"
    }

    for name, path in docs.items():
        if path.exists():
            size = path.stat().st_size
            # Validate non-trivial content (>500 bytes)
            if size < 500:
                state["documents"][name] = {"status": "error", "size": size, "error": "File too small"}
            else:
                state["documents"][name] = {"status": "ok", "size": size}
        else:
            state["documents"][name] = {"status": "missing", "size": 0}

    state["last_checked"] = datetime.now().isoformat()
    db.metadata.set_value(PLANNING_PROGRESS_KEY, state)
    return state


# Combined Planning Prompt - Integrates all Section 1 agents
COMBINED_PLANNING_PROMPT = """# Combined Planning Agent for Relay Framework

You are the Combined Planning Agent for the Relay Framework. You will complete Section 1 in TWO PHASES in THIS SINGLE SESSION.

---

# PHASE 1: REQUIREMENTS INTERVIEW (Interactive)

Conduct a conversational interview with the user to gather comprehensive project requirements.

**Interview Guidelines:**
- Be conversational, not questionnaire-style
- Ask follow-up questions based on responses
- Clarify ambiguities
- Keep it friendly and efficient (5-10 minutes)

**Topics to Cover:**

1. **Project Basics**
   - Project name
   - One-sentence description
   - Problem it solves
   - Target users/audience

2. **Core Features & Use Cases**
   - Main features (prioritized list)
   - User stories and workflows
   - Must-have vs nice-to-have features
   - Success metrics

3. **Technical Preferences**
   - Programming languages
   - Frontend framework (React, Vue, Angular, none?)
   - Backend framework (Express, FastAPI, Django, none?)
   - Database (PostgreSQL, MongoDB, SQLite?)
   - Hosting/deployment preferences
   - Third-party services/APIs

4. **Constraints & Requirements**
   - Timeline expectations
   - Budget considerations
   - Team size
   - Compliance needs (GDPR, HIPAA, SOC2, etc.)
   - Performance requirements
   - Scalability needs

5. **Security Priorities**
   - Authentication method (OAuth2, JWT, sessions?)
   - User roles and permissions
   - Data sensitivity
   - Specific security concerns

**IMPORTANT:** Do NOT write any files yet. Keep all information in memory for Phase 2.

After the interview, transition to Phase 2 automatically.

---

# PHASE 2: DOCUMENT GENERATION (Same Session)

Now generate FOUR documents based on the interview context.

## Document 1: docs/system_design.md

Write a comprehensive system design document with these sections:

### 1. Tech Stack Selection
- **Frontend**: Framework, libraries, build tools, styling
- **Backend**: Framework, runtime, key libraries
- **Database**: Type, ORM/ODM, migration strategy
- **APIs**: REST/GraphQL, documentation approach
- **DevOps**: Deployment, CI/CD, monitoring

### 2. High-Level Architecture
- System components (diagram in text format using boxes/arrows)
- Component responsibilities
- Data flow between components
- External integrations
- Scalability considerations

### 3. Database Schema
- Tables/collections with all fields
- Data types
- Relationships (one-to-many, many-to-many)
- Indexes for performance
- Sample data structure

### 4. API Specifications
- Authentication strategy
- Endpoint list with methods (GET/POST/etc.)
- Request/response formats
- Error handling approach
- Rate limiting strategy

### 5. Data Models
- Core domain objects
- Validation rules
- Business logic location
- State management approach

**Use the Write tool to create docs/system_design.md**

---

## Document 2: docs/security_policy.md

Write a comprehensive security policy with these sections:

### 1. Authentication & Authorization
- Method: OAuth2, JWT, sessions, etc. (SPECIFIC implementation)
- Multi-factor authentication requirements
- Password policy (min length, complexity, hashing algorithm with cost factor)
- Session management (timeout, refresh strategy)
- Role-Based Access Control (RBAC) implementation

### 2. Data Encryption Standards
- At-rest encryption: AES-256 for databases, disk encryption
- In-transit encryption: TLS 1.3 for all connections
- Key management strategy
- Secrets storage (environment variables, vault, etc.)

### 3. Forbidden Library List
Create a table of libraries to NEVER use:
| Library | Reason | Recommended Alternative |
|---------|--------|------------------------|
| md5 | Cryptographically broken | bcrypt, Argon2 |
| ... | ... | ... |

### 4. Input Validation & Sanitization
- **SQL Injection Prevention**: Use parameterized queries, ORMs
- **XSS Prevention**: Escape output, Content Security Policy
- **CSRF Prevention**: Tokens, SameSite cookies
- **File Upload Security**: Type validation, size limits, virus scanning
- **Path Traversal Prevention**: Whitelist directories, validate paths

### 5. OWASP Top 10 Compliance
Address each OWASP Top 10 vulnerability:
1. Broken Access Control → [specific measures]
2. Cryptographic Failures → [specific measures]
3. Injection → [specific measures]
4. Insecure Design → [specific measures]
5. Security Misconfiguration → [specific measures]
6. Vulnerable Components → [specific measures]
7. Identification/Authentication Failures → [specific measures]
8. Software/Data Integrity Failures → [specific measures]
9. Security Logging/Monitoring Failures → [specific measures]
10. Server-Side Request Forgery → [specific measures]

### 6. Secure Coding Guidelines
- Error handling (don't expose internals)
- Logging (what to log, what NOT to log)
- Rate limiting (requests per minute)
- Security headers (CSP, X-Frame-Options, etc.)
- Secrets management (never hardcode, use env vars)
- Dependency scanning (automated tools)

### 7. Security Testing Requirements
- **SAST**: Static analysis tools to use
- **DAST**: Dynamic testing approach
- **Dependency Scanning**: Tools and frequency
- **Penetration Testing**: Scope and schedule

**CRITICAL:** Be SPECIFIC and ACTIONABLE. Instead of "use strong hashing", say "use bcrypt.hash(password, 12)".

**Use the Write tool to create docs/security_policy.md**

---

## Document 3: docs/ui_standards.md

Write a comprehensive UI/UX design system document that frontend developers will reference for ALL UI implementation.

**IMPORTANT:** This document replaces task-specific wireframes. It must provide complete design guidance so frontend developers never need additional wireframe generation.

### 1. Design Language & Principles
- Overall design philosophy (modern, minimal, accessible, corporate, playful, etc.)
- Design principles (consistency, clarity, efficiency, user-centric)
- Brand personality and tone
- Target audience and use cases

### 2. Color Palette
Define a complete color system with HEX codes:

**Primary Colors:**
- Primary: #1E40AF (example)
- Primary Light: #3B82F6
- Primary Dark: #1E3A8A

**Secondary Colors:**
- Secondary: #10B981 (example)
- Secondary Light: #34D399
- Secondary Dark: #059669

**Neutral Colors:**
- White: #FFFFFF
- Gray 50-900: (8-10 shades)
- Black: #000000

**Semantic Colors:**
- Success: #10B981
- Warning: #F59E0B
- Error: #EF4444
- Info: #3B82F6

**Text Colors:**
- Heading: (dark gray or black)
- Body: (medium gray)
- Muted: (light gray)
- Inverse: (white for dark backgrounds)

**Background Colors:**
- Primary background: #FFFFFF
- Secondary background: #F9FAFB
- Card background: #FFFFFF
- Hover states: (light gray)

### 3. Typography
Define the complete typography system:

**Font Families:**
- Primary: 'Inter', sans-serif (or chosen font)
- Secondary: 'Roboto', sans-serif (if needed)
- Monospace: 'Fira Code', monospace (for code)

**Font Sizes:** (use consistent scale, e.g., 1.25 ratio)
- xs: 0.75rem (12px)
- sm: 0.875rem (14px)
- base: 1rem (16px)
- lg: 1.125rem (18px)
- xl: 1.25rem (20px)
- 2xl: 1.5rem (24px)
- 3xl: 1.875rem (30px)
- 4xl: 2.25rem (36px)
- 5xl: 3rem (48px)

**Font Weights:**
- Light: 300
- Regular: 400
- Medium: 500
- Semibold: 600
- Bold: 700

**Line Heights:**
- Tight: 1.25
- Normal: 1.5
- Relaxed: 1.75

**Letter Spacing:**
- Tight: -0.025em
- Normal: 0
- Wide: 0.025em

### 4. Spacing System
Define a consistent spacing scale (8px base):
- xs: 0.25rem (4px)
- sm: 0.5rem (8px)
- md: 1rem (16px)
- lg: 1.5rem (24px)
- xl: 2rem (32px)
- 2xl: 3rem (48px)
- 3xl: 4rem (64px)

**Usage Guidelines:**
- Padding: Use for internal spacing (within components)
- Margin: Use for external spacing (between components)
- Gap: Use for flexbox/grid spacing

### 5. Component Guidelines

#### Buttons
- **Primary Button**: Background color, text color, padding, border-radius, hover/active states
- **Secondary Button**: Outline style, colors, states
- **Text Button**: Minimal style, underline on hover
- **Sizes**: Small, Medium, Large (specific dimensions)
- **Disabled State**: Opacity, cursor, colors
- **Icon Buttons**: Size, padding, alignment

#### Forms
- **Input Fields**: Height, padding, border, focus state, error state
- **Textarea**: Min-height, max-height, resize behavior
- **Select Dropdowns**: Styling, arrow icon, options styling
- **Checkboxes**: Size, checked/unchecked styles, label spacing
- **Radio Buttons**: Size, selected state, label spacing
- **Form Labels**: Font size, weight, spacing from input
- **Error Messages**: Color, icon, placement, font size
- **Helper Text**: Color, font size, placement

#### Cards & Containers
- **Card**: Background, border, shadow, border-radius, padding
- **Container**: Max-width, padding, responsive behavior
- **Section**: Background, padding, margin

#### Navigation
- **Header/Navbar**: Height, background, padding, sticky behavior
- **Navigation Links**: Colors, hover states, active states
- **Sidebar**: Width, background, collapsed state
- **Breadcrumbs**: Colors, separators, font size

#### Modals & Dialogs
- **Modal**: Width, max-height, background, overlay color/opacity
- **Dialog**: Padding, title styling, button alignment
- **Close Button**: Position, size, icon

#### Tables & Lists
- **Table**: Border style, header background, row hover state, padding
- **Table Headers**: Font weight, background, border
- **Table Cells**: Padding, alignment, border
- **Lists**: Bullet/number style, spacing, nesting
- **List Items**: Padding, hover state

#### Alerts & Notifications
- **Alert Box**: Colors for success/warning/error/info, icon, padding, border-radius
- **Toast Notification**: Position, animation, duration, max-width
- **Banner**: Background, text color, dismiss button

### 6. Layout Patterns

#### Grid System
- Container max-width: 1280px (or chosen width)
- Column count: 12-column grid
- Gutter: 24px (or chosen spacing)
- Breakpoints: Mobile, Tablet, Desktop (see section 7)

#### Common Page Layouts

**Dashboard Layout:**
```
┌────────────────────────────────────────────────────────┐
│  Sidebar    │  Main Content Area                       │
│             │                                           │
│  Nav Items  │  ┌─────────────┐  ┌─────────────┐       │
│             │  │  Card 1     │  │  Card 2     │       │
│             │  └─────────────┘  └─────────────┘       │
│             │                                           │
│             │  ┌──────────────────────────────────┐    │
│             │  │  Data Table                      │    │
│             │  └──────────────────────────────────┘    │
└────────────────────────────────────────────────────────┘
```

**Form/Create-Edit Layout:**
```
┌────────────────────────────────────────────────────────┐
│  Header Navigation                          [Save] [Cancel] │
├────────────────────────────────────────────────────────┤
│                                                        │
│  ┌──────────────────────────────────────────────┐    │
│  │  Form Title                                   │    │
│  │                                               │    │
│  │  [Label]  [Input Field________________]      │    │
│  │  [Label]  [Input Field________________]      │    │
│  │  [Label]  [Textarea___________________       │    │
│  │           _____________________________       │    │
│  │           ___________________________]       │    │
│  │                                               │    │
│  │  [Label]  [Select Dropdown ▼]                │    │
│  │                                               │    │
│  │           [Submit Button]  [Cancel]          │    │
│  └──────────────────────────────────────────────┘    │
│                                                        │
└────────────────────────────────────────────────────────┘
```

**List/Table View Layout:**
```
┌────────────────────────────────────────────────────────┐
│  Header  [Search_______]  [Filter ▼]  [+ New]        │
├────────────────────────────────────────────────────────┤
│                                                        │
│  ┌──────────────────────────────────────────────┐    │
│  │ Column 1    │ Column 2    │ Column 3 │ Actions │  │
│  ├─────────────┼─────────────┼──────────┼─────────┤  │
│  │ Data        │ Data        │ Data     │ [Edit]  │  │
│  │ Data        │ Data        │ Data     │ [Edit]  │  │
│  │ Data        │ Data        │ Data     │ [Edit]  │  │
│  └──────────────────────────────────────────────┘    │
│                                                        │
│  [< Previous]  Page 1 of 5  [Next >]                  │
└────────────────────────────────────────────────────────┘
```

**Detail/View Page Layout:**
```
┌────────────────────────────────────────────────────────┐
│  Header Navigation                      [Edit] [Delete] │
├────────────────────────────────────────────────────────┤
│                                                        │
│  ┌──────────────────────────────────────────────┐    │
│  │  Title / Entity Name                          │    │
│  │  Status Badge  |  Last Updated: Date          │    │
│  ├──────────────────────────────────────────────┤    │
│  │                                               │    │
│  │  Field Label: Value                           │    │
│  │  Field Label: Value                           │    │
│  │  Field Label: Value                           │    │
│  │                                               │    │
│  │  Description:                                 │    │
│  │  Lorem ipsum dolor sit amet...                │    │
│  │                                               │    │
│  └──────────────────────────────────────────────┘    │
│                                                        │
│  ┌──────────────────────────────────────────────┐    │
│  │  Related Items / Activity Log                 │    │
│  └──────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────┘
```

### 7. Responsive Design

**Breakpoints:**
- Mobile: 0-767px (max-width: 767px)
- Tablet: 768px-1023px
- Desktop: 1024px+ (min-width: 1024px)

**Mobile-First Approach:**
- Start with mobile layout
- Enhance for larger screens using min-width media queries
- Stack elements vertically on mobile
- Use full-width components on mobile

**Responsive Behavior:**
- Navigation: Hamburger menu on mobile, full nav on desktop
- Grid: 1 column on mobile, 2-3 on tablet, 3-4 on desktop
- Font sizes: Slightly smaller on mobile (80-90% of desktop)
- Padding/Spacing: Reduce by 25-50% on mobile
- Tables: Horizontal scroll or card layout on mobile

### 8. Accessibility Standards

**WCAG 2.1 Level AA Compliance:**

**Color Contrast:**
- Normal text: Minimum 4.5:1 ratio
- Large text (18pt+ or 14pt+ bold): Minimum 3:1 ratio
- UI components: Minimum 3:1 ratio

**Keyboard Navigation:**
- All interactive elements must be keyboard accessible
- Visible focus indicators (outline or ring)
- Logical tab order
- Skip to main content link

**ARIA Labels and Roles:**
- Use semantic HTML first (nav, main, aside, article)
- Add ARIA labels for icon-only buttons
- Use aria-describedby for form errors
- Add role="alert" for dynamic messages
- Use aria-expanded for dropdowns/accordions

**Screen Reader Considerations:**
- Alt text for all images (empty alt="" for decorative)
- Form labels properly associated with inputs
- Error messages announced to screen readers
- Loading states announced (aria-live regions)

**Focus Management:**
- Maintain focus when opening/closing modals
- Return focus to trigger element when closing
- Focus first interactive element in modals
- Don't trap focus without escape mechanism

### 9. Additional Guidelines

**Shadows & Elevation:**
- sm: subtle shadow for cards
- md: moderate shadow for dropdowns
- lg: prominent shadow for modals
- Elevation hierarchy: base → cards → dropdowns → modals

**Border Radius:**
- sm: 0.25rem (4px) for buttons, inputs
- md: 0.375rem (6px) for cards
- lg: 0.5rem (8px) for modals
- full: 9999px for pills/badges

**Transitions & Animations:**
- Duration: 150-300ms for UI interactions
- Easing: ease-in-out for most transitions
- Hover: 150ms color/background transitions
- Modal: 200ms fade + scale animation

**Icons:**
- Icon library: (Heroicons, Feather, Material Icons, etc.)
- Size: 16px (sm), 20px (md), 24px (lg)
- Color: Inherit from text color or use semantic colors
- Always provide aria-label for icon-only buttons

**Use the Write tool to create docs/ui_standards.md**

---

## Document 4a: docs/master_plan.md

Write a human-readable master plan with:

### 1. Project Overview
- Project name and summary (from interview)
- Key objectives
- Success criteria
- Requirements summary (from interview context)

### 2. Implementation Phases
Break the project into 3-5 phases:
- Phase 1: Architecture & Foundation
- Phase 2: Core Features
- Phase 3: Additional Features
- Phase 4: Testing & Polish
- (etc.)

### 3. Task Breakdown per Phase
For each phase, list tasks with:
- Task ID (ARCH-001, BE-001, FE-001, etc.)
- Task title
- Brief description
- Dependencies (task IDs)
- Assigned role (frontend_developer or backend_developer)
- Complexity (1-5)

**Use the Write tool to create docs/master_plan.md**

---

## Document 4b: .relay/tasks.json

Create a JSON file with ALL implementation tasks.

**CRITICAL: Task Role Assignment**

Every task MUST be assigned to ONE of these roles:
- **frontend_developer**: UI components, pages, forms, styling, client-side logic, routing, state management
- **backend_developer**: API endpoints, database models, business logic, authentication, background jobs, integrations

**RULES:**
1. Do NOT use generic "developer" role - it doesn't exist
2. Do NOT use "fullstack_developer" - split into separate frontend/backend tasks
3. If a task involves both frontend and backend:
   - Split into TWO tasks (one frontend, one backend)
   - Use dependencies to sequence them
   - Example: "Create user API" (backend_developer) + "Create user profile page" (frontend_developer with dependency on API task)

**JSON Format:**

```json
{
  "project_name": "Project Name from Interview",
  "tasks": [
    {
      "id": "ARCH-001",
      "title": "Setup project structure and database schema",
      "description": "COMPREHENSIVE description with ALL context. See format below.",
      "phase": "architecture",
      "role": "backend_developer",
      "agent_type": "backend",
      "dependencies": [],
      "priority": 1,
      "complexity": 3
    },
    {
      "id": "FE-001",
      "title": "Create landing page component",
      "description": "COMPREHENSIVE description...",
      "phase": "core_features",
      "role": "frontend_developer",
      "agent_type": "frontend",
      "dependencies": ["ARCH-001"],
      "priority": 2,
      "complexity": 2
    }
  ]
}
```

**CRITICAL: Task Description Format**

Each task `description` field is the ONLY source of context for agents. Include:

1. **What to build/implement** - Specific, actionable instructions
2. **Acceptance criteria** - How to verify it's done correctly
3. **Dependencies explained** - Why this depends on other tasks
4. **SECTION 1 references** - Point to relevant docs:
   - "See docs/system_design.md section 3 for database schema"
   - "Follow authentication requirements in docs/security_policy.md section 1"
5. **Technical details** - Specific frameworks, libraries, patterns to use
6. **Security requirements** - Reference security policy if applicable
7. **For frontend tasks**: Reference docs/ui_standards.md for design system, colors, fonts, and layouts
8. **Agent type**: Always include agent_type field ('frontend' or 'backend')

**Good Example:**
```
"description": "Implement user authentication API using OAuth2 with JWT tokens. Follow security requirements in docs/security_policy.md section 1. Use bcrypt for password hashing (12 rounds as specified in security policy). Create POST /auth/login and POST /auth/logout endpoints per docs/system_design.md section 4. Store JWT secret in environment variable JWT_SECRET. Implement token refresh logic with 15-minute access token expiry. Acceptance: User can log in with email/password, receive JWT, and access protected routes. Frontend will call these endpoints from FE-002. Depends on ARCH-001 for user table schema."
```

**Bad Example:**
```
"description": "Add authentication"  ← Too vague, no context
```

**Use the Write tool to create .relay/tasks.json**

---

# Completion Checklist

Before finishing, verify you've created:
- ✅ docs/system_design.md
- ✅ docs/security_policy.md
- ✅ docs/ui_standards.md
- ✅ docs/master_plan.md
- ✅ .relay/tasks.json

If all five files are created, you're done! The framework will automatically convert tasks.json to the tasks.db database.
"""


def run_combined_planning(project_dir: Path) -> bool:
    """
    Run combined planning agent (interview + architecture + security + planning).

    This replaces the sequential Section 1 flow with a single interactive session.

    Args:
        project_dir: Project root directory

    Returns:
        True if successful, False otherwise
    """
    project_dir = Path(project_dir)

    print("\n" + "="*80)
    print("🎯 SECTION 1: COMBINED PLANNING AGENT")
    print("="*80)
    print("\nThis agent will complete Section 1 in ONE session:")
    print("  1. 📋 Interview you about project requirements (interactive)")
    print("  2. 🏗️  Generate system design document")
    print("  3. 🔒 Generate security policy document")
    print("  4. 🎨 Generate UI/UX design standards document")
    print("  5. 📝 Generate master plan + task breakdown")
    print("\nTime savings: ~50-65% faster than sequential agents!")
    print("\nLet's begin the interview...\n")

    # Check for partial completion and offer resume
    try:
        db = TaskDatabase(project_dir)
        existing_state = db.metadata.get_value(PLANNING_PROGRESS_KEY)

        if existing_state and existing_state.get("phase") in ["timeout", "failed"]:
            completed_docs = [k for k, v in existing_state["documents"].items() if v["status"] == "ok"]
            missing_docs = [k for k, v in existing_state["documents"].items() if v["status"] != "ok"]

            if len(completed_docs) > 0:
                print(f"\n⚠️  Found partial planning session:")
                print(f"  ✓ Completed: {', '.join(completed_docs)}")
                print(f"  ✗ Missing: {', '.join(missing_docs)}")
                print("\nOptions:")
                print("  1. Resume: Generate only missing documents")
                print("  2. Restart: Delete all and start fresh")
                choice = input("Choice (1/2): ").strip()

                if choice == "1":
                    print("\n⚠️  Resume feature not yet fully implemented.")
                    print("For now, please manually complete the missing documents or choose restart.")
                    return False
                elif choice == "2":
                    # Clear state and restart
                    db.metadata.set_value(PLANNING_PROGRESS_KEY, None)
                    print("\nRestarting planning from scratch...\n")
                else:
                    print("Invalid choice. Aborting.")
                    return False

        # Initialize fresh state
        init_planning_state(db)
    except Exception as e:
        logger.warning(f"Could not check for existing planning state: {e}")
        # Continue anyway

    # Get model ID for combined planner
    model_id = get_model_id_for_agent('combined_planner')
    logger.info(f"Launching Combined Planning agent (model: {model_id})...")

    try:
        # Run interactive Claude CLI session
        # Agent will interview user, then generate all documents in same session
        # NOTE: Output is shown in real-time so user can see interview progress
        process = subprocess.Popen(
            [
                "claude",
                "--model", model_id,
                "--dangerously-skip-permissions",  # Allow Write tool for document generation
                COMBINED_PLANNING_PROMPT
            ],
            cwd=str(project_dir),
            stdout=None,  # Inherit stdout - show output in real-time
            stderr=None,  # Inherit stderr - show errors in real-time
            stdin=None    # Inherit stdin - allow interactive input
        )

        # Wait for completion with timeout
        try:
            returncode = process.wait(timeout=2400)  # 40-minute timeout
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise

        if returncode != 0:
            logger.error(f"Combined planning agent failed with exit code {returncode}")
            return False

        # Verify all documents were created
        system_design_file = project_dir / "docs" / "system_design.md"
        security_policy_file = project_dir / "docs" / "security_policy.md"
        ui_standards_file = project_dir / "docs" / "ui_standards.md"
        master_plan_file = project_dir / "docs" / "master_plan.md"
        tasks_json_file = project_dir / ".relay" / "tasks.json"

        missing_files = []
        if not system_design_file.exists():
            missing_files.append("docs/system_design.md")
        if not security_policy_file.exists():
            missing_files.append("docs/security_policy.md")
        if not ui_standards_file.exists():
            missing_files.append("docs/ui_standards.md")
        if not master_plan_file.exists():
            missing_files.append("docs/master_plan.md")
        if not tasks_json_file.exists():
            missing_files.append(".relay/tasks.json")

        if missing_files:
            logger.error(f"Combined planning agent did not create: {', '.join(missing_files)}")
            return False

        logger.info("✅ All Section 1 documents created successfully!")
        logger.info(f"  - {system_design_file}")
        logger.info(f"  - {security_policy_file}")
        logger.info(f"  - {ui_standards_file}")
        logger.info(f"  - {master_plan_file}")
        logger.info(f"  - {tasks_json_file}")

        # Checkpoint successful document creation
        state = verify_and_checkpoint_documents(project_dir)

        # Convert tasks.json to tasks.db
        logger.info("Converting tasks.json to tasks database...")
        success = _populate_tasks_database(project_dir)

        if success:
            # Mark planning as completed
            try:
                db = TaskDatabase(project_dir)
                state["phase"] = "completed"
                state["completed_at"] = datetime.now().isoformat()
                db.metadata.set_value(PLANNING_PROGRESS_KEY, state)
            except Exception:
                pass  # Best effort checkpoint

            logger.info("✅ Task database populated successfully!")
            logger.info("🎉 Section 1 complete!")
            return True
        else:
            logger.error("❌ Failed to populate task database")
            return False

    except subprocess.TimeoutExpired:
        # Checkpoint progress before reporting error
        state = verify_and_checkpoint_documents(project_dir)
        state["phase"] = "timeout"
        state["error"] = "40-minute timeout"

        try:
            db = TaskDatabase(project_dir)
            db.metadata.set_value(PLANNING_PROGRESS_KEY, state)
        except Exception:
            pass  # Best effort checkpoint

        # Report which docs succeeded
        completed = [k for k, v in state["documents"].items() if v["status"] == "ok"]
        missing = [k for k, v in state["documents"].items() if v["status"] != "ok"]

        logger.error("Combined planning agent timed out (40-minute limit)")
        logger.error(f"Completed documents: {', '.join(completed) if completed else 'none'}")
        logger.error(f"Missing documents: {', '.join(missing)}")
        logger.error("This can happen if:")
        logger.error("  1. Interview took too long (try to keep responses concise)")
        logger.error("  2. Document generation is complex (normal for large projects)")
        logger.error("  3. Agent got stuck (check logs)")
        logger.error("\nTip: Run 'relay start' again to resume from where you left off")
        return False
    except Exception as e:
        # Checkpoint progress before reporting error
        try:
            state = verify_and_checkpoint_documents(project_dir)
            state["phase"] = "failed"
            state["error"] = str(e)
            db = TaskDatabase(project_dir)
            db.metadata.set_value(PLANNING_PROGRESS_KEY, state)
        except Exception:
            pass  # Best effort checkpoint

        logger.error(f"Combined planning agent failed: {e}")
        return False


def _populate_tasks_database(project_dir: Path) -> bool:
    """
    Populate tasks database from .relay/tasks.json

    Args:
        project_dir: Project root directory

    Returns:
        True if successful, False otherwise
    """
    tasks_json_file = project_dir / ".relay" / "tasks.json"

    if not tasks_json_file.exists():
        logger.error(f"tasks.json not found: {tasks_json_file}")
        return False

    try:
        # Read tasks.json
        with open(tasks_json_file, 'r') as f:
            tasks_data = json.load(f)

        # Validate format
        if 'tasks' not in tasks_data:
            logger.error("tasks.json missing 'tasks' array")
            return False

        tasks = tasks_data['tasks']
        logger.info(f"Found {len(tasks)} tasks in tasks.json")

        # Validate task quality (warnings only, not blockers)
        validation_warnings = _validate_task_descriptions(tasks)
        if validation_warnings:
            logger.warning("⚠️  Task quality issues detected (not blocking):")
            for warning in validation_warnings:
                logger.warning(f"  - {warning}")
            logger.warning("\nThese may cause agent failures during execution.")
            logger.warning("Consider regenerating with 'relay start' if issues persist.\n")

        # Initialize database
        db = TaskDatabase(project_dir)

        # Insert each task
        for task_data in tasks:
            # Validate required fields
            required_fields = ['id', 'title', 'description', 'phase', 'role']
            missing = [f for f in required_fields if f not in task_data]
            if missing:
                logger.warning(f"Task {task_data.get('id', 'unknown')} missing fields: {missing}")
                continue

            # Ensure agent_type is set (default to backend if not specified)
            if 'agent_type' not in task_data:
                # Infer from role
                if 'frontend' in task_data['role'].lower():
                    task_data['agent_type'] = 'frontend'
                else:
                    task_data['agent_type'] = 'backend'

            # Set initial status
            task_data['status'] = 'todo'

            # Create task
            db.create_task(task_data)

        # Verify tasks were created
        stats = db.get_statistics()
        logger.info(f"Database statistics: {stats}")

        if stats['total'] != len(tasks):
            logger.warning(f"Expected {len(tasks)} tasks, but database has {stats['total']}")

        return stats['total'] > 0

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in tasks.json: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to populate database: {e}")
        return False


def _validate_task_descriptions(tasks: list) -> list:
    """
    Validate task description quality.

    Returns list of warning messages (not errors - validation is non-blocking).

    Args:
        tasks: List of task dictionaries

    Returns:
        List of warning strings
    """
    warnings = []

    for idx, task_data in enumerate(tasks):
        task_id = task_data.get('id', f'task-{idx}')
        desc = task_data.get('description', '')

        # 1. Minimum length check
        if len(desc) < 200:
            warnings.append(
                f"{task_id}: Short description ({len(desc)} chars, recommend 200+)"
            )

        # 2. Must reference at least one docs/ file
        doc_refs = ['docs/system_design', 'docs/security_policy', 'docs/ui_standards']
        if not any(ref in desc for ref in doc_refs):
            warnings.append(
                f"{task_id}: No references to planning documents"
            )

        # 3. Should contain acceptance criteria
        if 'acceptance' not in desc.lower() and 'criteria' not in desc.lower():
            warnings.append(
                f"{task_id}: Missing acceptance criteria"
            )

        # 4. Frontend tasks should reference ui_standards
        role = task_data.get('role', '')
        if 'frontend' in role.lower() and 'ui_standards' not in desc:
            warnings.append(
                f"{task_id}: Frontend task missing UI standards reference"
            )

        # 5. Security-sensitive tasks should reference security_policy
        security_keywords = ['auth', 'login', 'password', 'encrypt', 'permission', 'token']
        if any(kw in desc.lower() for kw in security_keywords) and 'security_policy' not in desc:
            warnings.append(
                f"{task_id}: Security-sensitive task missing security policy reference"
            )

    return warnings
