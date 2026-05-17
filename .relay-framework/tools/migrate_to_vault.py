#!/usr/bin/env python3
"""
Migrate from docs/codex.md to vault structure
==============================================

Splits monolithic codex into domain-specific vault files.
Preserves docs/system_design.md, security_policy.md, ui_standards.md.
"""

import sys
from pathlib import Path
from datetime import datetime


def create_vault_structure(project_dir: Path):
    """Create vault directory structure."""

    vault_dir = project_dir / ".relay" / "vault"

    # Create directories
    dirs = [
        vault_dir,
        vault_dir / "planning",        # Section 1 planning docs
        vault_dir / "architecture",
        vault_dir / "frontend",
        vault_dir / "backend",
        vault_dir / "integrations",
        vault_dir / "security",
        vault_dir / "decisions",
    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"✓ Created {d.relative_to(project_dir)}")

    return vault_dir


def create_index_files(vault_dir: Path):
    """Create index files for each domain."""

    # Domain descriptions (only for domains that exist)
    domain_descriptions = {
        "planning": "Section 1 planning docs (system design, security policy, UI standards, master plan)",
        "architecture": "System design, database schema, API standards, tech stack",
        "frontend": "Pages, components, UI standards, design system",
        "backend": "API endpoints, services, business logic",
        "integrations": "Third-party services and integrations",
        "security": "Authentication, authorization, security policies",
        "decisions": "Architecture Decision Records (ADRs)",
    }

    # Dynamically build domain table based on what exists
    domain_rows = []
    for domain_folder in sorted(vault_dir.iterdir()):
        if domain_folder.is_dir() and not domain_folder.name.startswith("."):
            domain_name = domain_folder.name
            description = domain_descriptions.get(domain_name, "Domain documentation")
            # Capitalize domain name for display
            display_name = domain_name.replace("_", " ").title()
            domain_rows.append(f"| [{display_name}]({domain_name}/index.md) | {description} |")

    domains_table = "\n".join(domain_rows)

    # Main index
    main_index = """# Project Vault Index

Last Updated: {date}

This vault contains all architectural documentation, design standards, and **implementation details for what IS ALREADY BUILT** in the project.

**CRITICAL:** This vault documents the **CURRENT STATE**, not future plans:
- ✅ **What EXISTS** - APIs implemented, pages deployed, integrations working
- ❌ **What's PLANNED** - Stored in `planning/master_plan.md` (future roadmap)

**Exception:** The `decisions/` folder contains ADRs that can have status "Proposed" (discussing what to build) or "Accepted" (documenting decisions made).

## Domains

| Domain | Description |
|--------|-------------|
{domains_table}

## Quick Links

- [Changelog](CHANGELOG.md) - All updates to the vault
- [System Design](planning/system_design.md) - Overall architecture (Section 1)
- [Security Policy](planning/security_policy.md) - Security standards (Section 1)
- [UI Standards](planning/ui_standards.md) - Design system (Section 1)
- [Master Plan](planning/master_plan.md) - Future roadmap and improvement tasks
- [Tech Stack](architecture/tech-stack.md) - Technologies and frameworks used
- [Database Schema](architecture/database-schema.md) - Database tables and relationships
- [API Endpoints](backend/api-endpoints.md) - All REST/GraphQL endpoints

## How to Use This Vault

- **For developers**: Read the relevant domain docs before working on a task
- **For updates**: Update the specific domain file + add entry to CHANGELOG.md
- **For decisions**: Create an ADR in decisions/ and link from changelog
- **For Obsidian**: Open this folder as an Obsidian vault to view the knowledge graph
""".format(date=datetime.now().strftime("%Y-%m-%d"), domains_table=domains_table)

    (vault_dir / "INDEX.md").write_text(main_index)
    print(f"✓ Created INDEX.md with {len(domain_rows)} domains")

    # Changelog
    changelog = """# Project Changelog

All notable changes to the project architecture and **implementation** are documented here.

**IMPORTANT:** This changelog tracks what was BUILT/CHANGED, not what was planned.

## Format

Each entry includes:
- **Date** - When the change was IMPLEMENTED (not planned)
- **Change** - What was BUILT/CHANGED (present tense: "Added API endpoint", not "Will add")
- **Files Modified** - Which vault files were updated
- **ADR** - Link to ADR if applicable (can be Proposed or Accepted)
- **Description** - Implementation details (what exists now)

## Entries

| Date | Change | Files Modified | ADR | Description |
|------|--------|----------------|-----|-------------|
| {date} | Initial vault creation | All vault files | N/A | Migrated from monolithic docs/codex.md to domain-specific vault structure for better maintainability and targeted context injection. |

""".format(date=datetime.now().strftime("%Y-%m-%d"))

    (vault_dir / "CHANGELOG.md").write_text(changelog)
    print(f"✓ Created CHANGELOG.md")

    # Domain indexes
    domain_indexes = {
        "planning/index.md": """# Planning

Section 1 planning documents (requirements, standards, roadmap).

**NOTE:** These are from the initial planning phase (interview or analysis).
They define requirements and standards, not implementation details.

## Files

- [system_design.md](system_design.md) - Overall system architecture, tech stack decisions, database schema, API specs
- [security_policy.md](security_policy.md) - Security standards, authentication requirements, forbidden libraries
- [ui_standards.md](ui_standards.md) - Design system, colors, typography, component guidelines
- [master_plan.md](master_plan.md) - Future roadmap and improvement tasks (FUTURE PLANS)
""",
        "architecture/index.md": """# Architecture

System design, database schema, API standards, and tech stack **AS IMPLEMENTED**.

**NOTE:** This documents what EXISTS, not what's planned. Use present tense.

## Files

- [system-design.md](system-design.md) - Overall system architecture (from Section 1/Analyzer)
- [database-schema.md](database-schema.md) - Database tables that exist NOW
- [api-standards.md](api-standards.md) - API patterns currently in use
- [tech-stack.md](tech-stack.md) - Technologies actually installed and configured
""",
        "frontend/index.md": """# Frontend

Pages, components, UI standards, and design system **AS IMPLEMENTED**.

**NOTE:** Documents what EXISTS (pages deployed, components built). Present tense only.

## Files

- [ui-standards.md](ui-standards.md) - Design system currently in use (from Section 1/Analyzer)
- [pages.md](pages.md) - Pages that exist and are accessible
- [components.md](components.md) - Components actually built and reusable
""",
        "backend/index.md": """# Backend

API endpoints, services, and business logic **AS IMPLEMENTED**.

**NOTE:** Documents endpoints that WORK, services that EXIST. Present tense only.

## Files

- [api-endpoints.md](api-endpoints.md) - REST/GraphQL endpoints that are live
- [services.md](services.md) - Business logic services that are implemented
""",
        "integrations/index.md": """# Integrations

Third-party services and external APIs.

## Files

- [integrations.md](integrations.md) - All third-party integrations
""",
        "security/index.md": """# Security

Authentication, authorization, and security policies.

## Files

- [security-policy.md](security-policy.md) - Security standards and requirements
- [authentication.md](authentication.md) - Auth implementation
""",
        "decisions/index.md": """# Architecture Decision Records

ADRs document significant architectural decisions.

**NOTE:** This is the ONLY folder that can contain "Proposed" status (discussing what to build).
All other vault folders document what IS ALREADY BUILT.

## Format

Each ADR includes:
- **Context** - What is the issue we're facing?
- **Decision** - What did we decide?
- **Consequences** - What are the trade-offs?
- **Status** - Proposed (discussing) | Accepted (decided) | Superseded (replaced)

## Status Evolution

- **Proposed** → Discussion/proposal phase (not yet implemented)
- **Accepted** → Decision made (may or may not be implemented yet)
- **Superseded** → Replaced by a newer decision

When implementation completes, update the ADR to reference which vault files document the implementation.

## ADRs

- [adr-template.md](adr-template.md) - Template for new ADRs
"""
    }

    for filename, content in domain_indexes.items():
        path = vault_dir / filename
        path.write_text(content)
        print(f"✓ Created {filename}")


def migrate_docs_to_vault(project_dir: Path, vault_dir: Path):
    """Move existing docs into vault."""

    docs_dir = project_dir / "docs"

    # Map of doc files to vault locations (now in planning/)
    migrations = {
        "system_design.md": "planning/system_design.md",
        "security_policy.md": "planning/security_policy.md",
        "ui_standards.md": "planning/ui_standards.md",
        "master_plan.md": "planning/master_plan.md",
    }

    for src_name, dst_name in migrations.items():
        src = docs_dir / src_name
        dst = vault_dir / dst_name

        if src.exists():
            content = src.read_text()
            dst.write_text(content)
            print(f"✓ Migrated {src_name} → vault/{dst_name}")
        else:
            print(f"⚠ Skipped {src_name} (not found)")


def split_codex(project_dir: Path, vault_dir: Path):
    """Split codex.md into domain-specific files."""

    codex_path = project_dir / "docs" / "codex.md"

    if not codex_path.exists():
        print("⚠ No codex.md found, skipping split")
        return

    print(f"\n📝 Splitting codex.md into vault files...")
    print(f"   This will create initial content in:")
    print(f"   - vault/architecture/tech-stack.md")
    print(f"   - vault/architecture/database-schema.md")
    print(f"   - vault/backend/api-endpoints.md")
    print(f"   - vault/frontend/pages.md")
    print(f"   - vault/frontend/components.md")
    print(f"   - vault/integrations/integrations.md")
    print(f"\n   You should manually review and organize the content.")

    # Create placeholder files with concise format examples
    placeholders = {
        "architecture/tech-stack.md": """# Tech Stack

**Format: ONE LINE per technology**
`Technology` - Purpose, version

## Example
- PostgreSQL 16 - Primary database with pgvector for embeddings
- Node.js 20 - Backend runtime
- React 18 - Frontend UI library
""",
        "architecture/database-schema.md": """# Database Schema

**Format: ONE LINE per table**
`table_name` - Columns, indexes, relationships

## Example
- users - email (unique), password_hash, created_at, index on email
""",
        "backend/api-endpoints.md": """# API Endpoints

**Format: ONE LINE per endpoint**
`METHOD /path` - What it does, auth (yes/no), returns what

## Example
- `POST /api/users` - Creates user with validation, no auth, returns 201/user or 400/errors
- `GET /api/users/:id` - Fetches user by ID, requires JWT, returns 200/user or 404
""",
        "frontend/pages.md": """# Pages

**Format: ONE LINE per page**
`/route` - What user sees/does, key tech

## Example
- `/dashboard` - Metrics cards + chart, React Query + Recharts, requires auth
- `/login` - Email/password form, redirects to dashboard on success
""",
        "frontend/components.md": """# Components

**Format: ONE LINE per component**
`<ComponentName>` - What it renders, key features

## Example
- `<Button>` - Primary/secondary/ghost variants, loading state, accessible
- `<Modal>` - Overlay dialog, click outside to close, focus trap
""",
        "integrations/integrations.md": """# Integrations

**Format: ONE LINE per integration**
Service - What it does, auth method, key API calls

## Example
- Stripe - Payment processing, API key auth, charges.create() + webhooks
- SendGrid - Email delivery, API key auth, mail.send()
""",
    }

    for filename, content in placeholders.items():
        path = vault_dir / filename
        if not path.exists():
            path.write_text(content)
            print(f"✓ Created placeholder {filename}")


def create_adr_template(vault_dir: Path):
    """Create ADR template."""

    template = """# ADR-XXX: [Title]

**Date**: YYYY-MM-DD
**Status**: Proposed | Accepted | Superseded

## Context

What is the issue we're facing? What constraints exist?

## Decision

What did we decide to do?

## Consequences

What are the trade-offs of this decision?

### Positive
- Benefit 1
- Benefit 2

### Negative
- Drawback 1
- Drawback 2

## Alternatives Considered

What other options did we evaluate?

### Option A
- Pros: ...
- Cons: ...
- Why rejected: ...

## References

- Link to related discussions
- Link to related ADRs
"""

    path = vault_dir / "decisions" / "adr-template.md"
    path.write_text(template)
    print(f"✓ Created ADR template")


def main():
    if len(sys.argv) < 2:
        print("Usage: python migrate_to_vault.py <project_dir>")
        sys.exit(1)

    project_dir = Path(sys.argv[1]).resolve()

    if not project_dir.exists():
        print(f"Error: Project directory not found: {project_dir}")
        sys.exit(1)

    print("\n" + "="*80)
    print("VAULT MIGRATION")
    print("="*80)
    print(f"\nProject: {project_dir}")
    print(f"Creating vault structure at: {project_dir}/.relay/vault\n")

    # Create structure
    vault_dir = create_vault_structure(project_dir)

    # Create index files
    create_index_files(vault_dir)

    # Migrate existing docs
    migrate_docs_to_vault(project_dir, vault_dir)

    # Split codex (create placeholders)
    split_codex(project_dir, vault_dir)

    # Create ADR template
    create_adr_template(vault_dir)

    print("\n" + "="*80)
    print("✅ VAULT MIGRATION COMPLETE")
    print("="*80)
    print(f"\nVault created at: {vault_dir}")
    print(f"\nNext steps:")
    print(f"  1. Review and organize content from codex.md into vault files")
    print(f"  2. Update .relay-framework/core/executor.py to use vault context")
    print(f"  3. Update .relay-framework/core/codex_writer.py to update vault files")
    print(f"  4. Test with a few tasks to ensure context injection works")
    print()


if __name__ == "__main__":
    main()
