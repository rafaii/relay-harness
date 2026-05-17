# Vault System Documentation

## Overview

The Relay Framework uses a **vault-based documentation system** to replace the monolithic `docs/codex.md` with domain-specific files that scale better and enable targeted context injection.

## Architecture

### Two-Tier Documentation

1. **Section 1 Planning Docs** (`docs/`) - Requirements and standards
   - `system_design.md` - Overall architecture, tech decisions
   - `security_policy.md` - Security standards and requirements
   - `ui_standards.md` - Design system, colors, typography
   - `master_plan.md` - **Future plans** and improvement roadmap

2. **Vault** (`.relay/vault/`) - **Current implementation reality**
   - Domain-specific documentation of what IS BUILT
   - Present tense, facts only
   - Updated as tasks complete

## Vault Structure

```
.relay/vault/
├── INDEX.md                     # Main navigation
├── CHANGELOG.md                 # All implementation changes
├── architecture/
│   ├── index.md
│   ├── tech-stack.md           # Technologies installed/configured
│   └── database-schema.md      # Tables that exist
├── backend/
│   ├── index.md
│   ├── api-endpoints.md        # Endpoints that work
│   └── services.md             # Services that exist
├── frontend/
│   ├── index.md
│   ├── pages.md                # Pages that are deployed
│   └── components.md           # Components that are built
├── integrations/
│   ├── index.md
│   └── integrations.md         # Integrations that work
├── security/
│   ├── index.md
│   └── authentication.md       # Auth that exists
└── decisions/
    ├── index.md
    ├── adr-template.md
    └── adr-001-example.md      # Can be Proposed/Accepted
```

## Critical Rules

### Vault Content = Current State

✅ **DO document:**
- What IS built (present tense: "The API has", "Users can")
- Facts about current implementation
- Actual code that exists in the codebase

❌ **DO NOT document:**
- What WILL be built (future plans)
- TODOs or planned features
- Task IDs or phase names

### Exception: decisions/

The `decisions/` folder is the ONLY place that can contain "Proposed" status (discussing what to build). All other vault folders document implementation reality.

### Future Plans Go in master_plan.md

- Vault = "What we have"
- master_plan.md = "What we need"

## How Vault is Generated

### For Existing Projects (Analyzer)

When you run `relay analyze` on an existing codebase:

1. **Analyzer agent** scans the code
2. Generates Section 1 docs (system_design, security_policy, ui_standards, master_plan)
3. **Generates initial vault** from actual code:
   - tech-stack.md from package.json, requirements.txt
   - database-schema.md from models, migrations
   - api-endpoints.md from route files
   - pages.md from component/page files
   - etc.
4. User approves tasks → execution begins

### For New Projects (Combined Planner)

When you run `relay start` on a new project:

1. **Combined Planner** runs Section 1 interview
2. Generates Section 1 docs (requirements)
3. Vault starts **empty** (no implementation yet)
4. As tasks complete, **Vault Writer** appends entries

### During Execution (Vault Writer)

Every time a task completes with `status='done'`:

1. Vault Writer determines which vault files to update (based on role + keywords)
2. Spawns Claude to generate ONLY the new entry (50-200 words)
3. Appends entry to specific vault file
4. Updates CHANGELOG.md
5. Takes ~10-30 seconds (vs 5 minutes for old codex)

## Context Injection

### Agent Context (Vault Context Manager)

When an agent starts a task:

1. **VaultContextManager** determines relevant vault files based on:
   - Agent role (backend → api-endpoints.md, database-schema.md)
   - Task keywords (database → database-schema.md, auth → authentication.md)

2. Reads ONLY relevant vault files (~1,500-2,000 tokens vs 13,000+ for full codex)

3. Injects targeted context into agent prompt

### Role Mappings

- **backend_developer** → api-endpoints, services, database-schema, authentication
- **frontend_developer** → ui-standards, pages, components, api-endpoints
- **qa** → api-endpoints, pages, security-policy
- **security** → security-policy, authentication, api-endpoints, integrations
- **database** → database-schema, services
- **devops** → tech-stack, integrations, security-policy

## Migration

### Migrating Existing Projects

For projects still using `docs/codex.md`:

```bash
python3 .relay-framework/tools/migrate_to_vault.py /path/to/project
```

This creates vault structure and moves existing docs into vault.

### Backward Compatibility

The system is **backward compatible**:

- If vault exists → use vault context
- If vault doesn't exist → fall back to codex summaries
- Both can coexist during migration

## Benefits

### vs. Monolithic Codex

| Aspect | Old Codex | New Vault |
|--------|-----------|-----------|
| **Size** | 13,000+ tokens | 1,500-2,000 tokens (targeted) |
| **Update time** | 5 minutes | 10-30 seconds |
| **Timeouts** | Frequent | Never |
| **Context** | Everything | Only what's needed |
| **Scalability** | Grows infinitely | Scales to 100+ files |
| **Maintainability** | Hard to find sections | Easy domain navigation |
| **Updates** | Regenerate entire file | Append to specific file |

### Key Advantages

1. **10x faster updates** - Surgical appends instead of full regeneration
2. **Targeted context** - Agents get only relevant domains
3. **Scales infinitely** - Can grow to 100+ vault files without bloating prompts
4. **Better organization** - Find info by domain, not searching one huge file
5. **Audit trail** - CHANGELOG.md tracks all changes
6. **Separation of concerns** - Requirements (docs/) vs reality (vault/)

## Implementation Status

✅ **Complete:**
- Step 1: Vault structure and migration tool
- Step 2: Vault context injection (VaultContextManager)
- Step 3: Vault writer (targeted updates)
- Step 4: Analyzer generates vault for existing projects

✅ **No changes needed:**
- Step 5: Combined Planner already generates Section 1 docs correctly

## Usage

### For Users

**Analyzing existing project:**
```bash
relay analyze
```
→ Generates Section 1 docs + vault structure from code

**Starting new project:**
```bash
relay start
```
→ Section 1 interview → master_plan → execution → vault builds incrementally

**Migrating old project:**
```bash
python3 .relay-framework/tools/migrate_to_vault.py .
```
→ Creates vault structure from existing docs

### For Developers

**Reading vault files:**
```python
from core.vault_context import VaultContextManager

vault = VaultContextManager(project_dir)
context = vault.get_context_for_agent("backend_developer", task_description)
```

**Writing vault files:**
```python
from core.vault_writer import update_vault

await update_vault(project_dir, task_id, task_data)
```

## Best Practices

### Writing Vault Entries

✅ **Good:**
```markdown
### POST /api/users

Creates a new user account. Requires email and password. Returns 201 with user object or 400 with validation errors.

**Fields:**
- email (required, unique)
- password (required, 8+ chars)
```

❌ **Bad:**
```markdown
### POST /api/users (TODO)

Will create user accounts. Planned features:
- Email validation (BE-001)
- Password hashing (BE-002)
```

### Updating Vault

- Let Vault Writer handle updates automatically
- Don't manually edit vault files during execution
- Manual edits are fine before starting execution
- Keep entries concise (50-200 words)

## Troubleshooting

### Vault not found

If you see "Vault doesn't exist yet":
```bash
python3 .relay-framework/tools/migrate_to_vault.py /path/to/project
```

### Old project using codex

System will automatically fall back to codex summaries until you migrate.

### Vault update timeout

Vault updates timeout after 30 seconds. If this happens, check:
- Is Claude CLI working? (`claude --version`)
- Is the task log too large? (Vault Writer reads last 2000 chars)

## Future Enhancements

Potential improvements:

1. **Semantic search** - ChromaDB indexing for vault files
2. **Diff tracking** - Show what changed in each vault update
3. **Vault UI** - Web interface for browsing vault
4. **Auto-linking** - Detect references between vault files
5. **Vault validation** - Check for missing sections, broken links

## Related Files

- `core/vault_context.py` - Context manager for reading vault
- `core/vault_writer.py` - Writer for updating vault
- `core/analyzer.py` - Generates vault for existing projects
- `core/executor.py` - Uses vault context and writer
- `tools/migrate_to_vault.py` - Migration tool
