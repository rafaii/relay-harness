Here's a production-quality README based on everything we've analyzed about the actual framework:

---

```markdown
# Relay 🏃

> Pass the baton. Drop the baggage.

Relay is a multi-agent AI development harness that coordinates specialized AI agents to build software autonomously. Each agent runs a focused task, writes its output to structured files, and hands off cleanly to the next — no bloated context, no hallucination from session overload.

---

## How It Works

Relay splits development into two sections:

**Section 1 — Planning**
An interactive AI session interviews you about your project, then generates four critical planning documents and decomposes your requirements into an ordered, dependency-linked task database.

**Section 2 — Execution**
An async Python orchestrator polls the task database and dispatches up to 5 specialized AI agents in parallel. Each agent receives only the context relevant to its task, completes its work, and signals completion. Dependent tasks unlock automatically.
```

You ──► Combined Planner ──► tasks.db
│
┌─────────────────┼─────────────────┐
▼ ▼ ▼
[Architect] [Backend Dev] [Frontend Dev] ← up to 5 parallel
│ │ │
└────────────────►▼◄────────────────┘
[QA Engineer]
│
[Security Audit]
│
✅ Complete

````

---

## Agent Roster

| Agent | Role | When Invoked |
|---|---|---|
| **Combined Planner** | PRD interview, architecture, task decomposition | Section 1 — once per project |
| **Architect** | System design decisions, technical approach | Complex features needing design |
| **Backend Developer** | API endpoints, database models, business logic | All backend tasks |
| **Frontend Developer** | UI components, pages, client-side logic | All frontend tasks |
| **QA Engineer** | Test writing, bug detection, acceptance validation | After every dev task |
| **Security Officer** | OWASP audit, vulnerability assessment | After QA passes |
| **Codebase Analyzer** | Scans existing code, derives planning docs | Existing projects |

---

## Getting Started

### Prerequisites

- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/claude-code) installed and authenticated
- Node.js (if working on JS/TS projects)

### Installation

```bash
git clone https://github.com/rafaii/relay-harness
cd relay-harness
chmod +x install.sh
./install.sh
````

The installer:

- Copies the `.relay-framework/` to `~/.relay-framework/`
- Creates the `relay` CLI command at `/usr/local/bin/relay`
- Installs Python dependencies

### Starting a New Project

```bash
mkdir my-project && cd my-project
relay start
```

Relay detects no existing code and launches the Combined Planner. You'll have a short interview about your project — what you're building, who it's for, tech stack preferences. When you're done, Relay generates:

```
docs/
  system_design.md      # Architecture, DB schema, API contracts
  security_policy.md    # Auth approach, OWASP compliance rules
  ui_standards.md       # Component library, design tokens, layout patterns
  master_plan.md        # Phased feature roadmap
.relay/
  tasks.db              # SQLite task queue with dependencies
```

Section 2 starts automatically.

### Applying Relay to an Existing Project

```bash
cd your-existing-project
relay analyze
```

The Codebase Analyzer scans your source files, infers your architecture, tech stack, DB schemas, and API patterns — then generates the same four planning documents from your actual code rather than an interview. You review the proposed improvement tasks and approve before anything runs.

### Adding Features to an Existing Project

```bash
relay request "Add user profile editing with avatar upload"
relay request "Bug: Login fails when email has uppercase letters"
relay request "Feature: Add Stripe payment integration"
```

The Request Agent analyzes your request against existing planning docs, determines if any architecture updates are needed, generates focused tasks, and (with your approval) starts executing immediately. Works for new features, bug fixes, improvements, and tech debt.

---

## The Task Database

Every unit of work lives in `tasks.db` as a structured task:

| Field                       | Purpose                                                                  |
| --------------------------- | ------------------------------------------------------------------------ |
| `id`                        | Unique task identifier (e.g., `AUTH-001`)                                |
| `title`                     | Short human-readable label                                               |
| `description`               | 200+ character brief with acceptance criteria and doc references         |
| `status`                    | `todo → in_progress → done` (or `failed`, `blocked`)                     |
| `role`                      | Which agent handles it (`backend_developer`, `frontend_developer`, etc.) |
| `agent_type`                | Routing key for the orchestrator                                         |
| `dependencies`              | Comma-separated task IDs that must complete first                        |
| `phase`                     | `foundation → features → integration → polish`                           |
| `priority`                  | Higher number = dispatched first (auto-set by phase)                     |
| `complexity`                | 1–5 scale, used for agent timeout budgeting                              |
| `assignee`                  | Which agent slot currently holds the task                                |
| `created_at` / `updated_at` | Audit timestamps                                                         |

Dependencies are enforced by the scheduler — a task will not dispatch until all its prerequisite task IDs are marked `done`.

---

## The Four Planning Documents

These documents are the shared knowledge base for all agents. Every agent reads only the sections relevant to its task rather than receiving the entire codebase.

### `docs/system_design.md`

The technical blueprint. Covers database schema, API contracts, authentication flow, third-party integrations, and infrastructure decisions. The backend developer and architect reference this on every task.

### `docs/security_policy.md`

Security rules derived from your project's threat model. Covers authentication requirements, input validation standards, OWASP Top 10 mitigations, and compliance considerations. The security agent uses this as its audit checklist.

### `docs/ui_standards.md`

Your design system. Covers color palette, typography scale, component library choices, spacing conventions, accessibility requirements, and layout patterns. Every frontend task references this to ensure visual consistency.

### `docs/master_plan.md`

The product roadmap broken into phases. Tracks which features are planned, in progress, and complete. Updated as tasks are completed.

---

## Project Modes

Relay detects your project state automatically on every run:

| Mode        | Condition                          | Action                                     |
| ----------- | ---------------------------------- | ------------------------------------------ |
| `new`       | No source code, no relay docs      | Full planning interview → Section 2        |
| `existing`  | Source code present, no relay docs | `relay analyze` → review tasks → Section 2 |
| `resume`    | Relay docs exist, tasks incomplete | Skip Section 1, resume Section 2           |
| `completed` | All tasks done                     | Shows summary, prompts for next steps      |

---

## Parallel Execution

Section 2 runs up to **5 agents concurrently**. The orchestrator dispatches tasks based on:

1. **Dependencies met** — all prerequisite tasks are `done`
2. **Phase ordering** — `foundation` phase completes before `features` phase begins
3. **Priority** — higher priority tasks are dispatched first within the same phase
4. **Agent slot availability** — maximum 5 active Claude processes at once

Each agent works in its own scoped directory and writes to its own task file, preventing conflicts between parallel sessions.

---

## Commands

```bash
relay start              # Start or resume a project
relay analyze            # Analyze existing codebase (generates planning docs)
relay request "..."      # Add new feature/bug/improvement to existing project
relay status             # Show task completion stats and active agents
relay ui                 # Open the web dashboard at localhost:8888
relay resume             # Resume Section 2 after a crash or manual pause
relay reset              # Clear tasks.db and re-run Section 2 (keeps planning docs)
relay --help             # Full command reference
```

### Options

```bash
relay start --max-agents 3    # Limit concurrent agents (default: 5)
relay start --model sonnet    # Override default model for all agents
```

---

## Web Dashboard

```bash
relay ui
```

Opens a FastAPI-powered dashboard at `http://localhost:8888` showing:

- Live task status board grouped by phase
- Active agent slots with current task
- Completion percentage and ETA
- Per-task activity log

---

## Configuration

Project-level configuration lives at `.relay/config.json`:

```json
{
  "project_name": "My Project",
  "max_agents": 5,
  "default_model": "claude-sonnet-4-5",
  "agent_models": {
    "planner": "claude-sonnet-4-5",
    "architect": "claude-sonnet-4-5",
    "backend": "claude-sonnet-4-5",
    "frontend": "claude-sonnet-4-5",
    "qa": "claude-haiku-4-5",
    "security": "claude-sonnet-4-5",
    "analyzer": "claude-sonnet-4-5"
  }
}
```

Using `claude-haiku` for QA and cheaper agents for routine tasks can significantly reduce costs without impacting output quality.

---

## Project Structure

After a full run, your project will look like:

```
your-project/
├── src/                        # Your actual code (written by agents)
├── docs/
│   ├── system_design.md        # Architecture reference
│   ├── security_policy.md      # Security rules
│   ├── ui_standards.md         # Design system
│   └── master_plan.md          # Product roadmap
├── .relay/
│   ├── tasks.db                # SQLite task queue
│   ├── config.json             # Project configuration
│   ├── tasks/                  # Per-task markdown logs
│   │   ├── AUTH-001.md
│   │   ├── BE-001.md
│   │   └── ...
│   └── logs/                   # Agent execution logs
└── .relay-framework/           # Framework source (do not edit)
```

---

## How Agents Hand Off

Every agent follows the same read → execute → write → signal protocol:

1. **Read** `project_state` and its assigned task from `tasks.db`
2. **Read** only the relevant sections from the planning docs
3. **Execute** — writes code, tests, or documentation
4. **Write** its output and a summary to `.relay/tasks/{task_id}.md`
5. **Update** task status to `done` in `tasks.db`
6. **Signal** `===RELAY_AGENT_COMPLETE===` — the orchestrator detects this and dispatches the next ready task

No agent has awareness of what other agents are currently doing. Coordination happens entirely through the task database.

---

## Failure Handling

| Failure Type        | Behaviour                                                                                     |
| ------------------- | --------------------------------------------------------------------------------------------- |
| Agent timeout       | Task marked `failed`, logged, framework continues with other tasks                            |
| QA failure          | QA creates a `FIX-{task_id}` task; original task marked `blocked` until fix is done           |
| Security failure    | Same as QA — fix task created, dependents blocked                                             |
| Planning crash      | Checkpoint saved to `.relay/section1_progress.json`; `relay resume` retries missing docs only |
| Manual interruption | `relay resume` picks up from last completed task                                              |

---

## Requirements

```
python >= 3.10
claude-code CLI (authenticated)
chromadb
fastapi
uvicorn
pexpect
playwright (optional, for browser-based QA tasks)
```

Install all Python dependencies:

```bash
pip install -r .relay-framework/requirements.txt
```

---

## License

MIT — use it, fork it, build on it.

---

## Philosophy

Most agent frameworks try to keep one giant AI session alive for the duration of a project. Relay does the opposite: **each agent is amnesia by design**. A fresh Claude process with a focused task and minimal context outperforms a bloated session every time. The baton passes. The baggage stays behind.

```

```
