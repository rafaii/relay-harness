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

    # Main index
    main_index = """# Project Vault Index

Last Updated: {date}

This vault contains all architectural documentation, design standards, and **implementation details for what IS ALREADY BUILT** in the project.

**CRITICAL:** This vault documents the **CURRENT STATE**, not future plans:
- ✅ **What EXISTS** - APIs implemented, pages deployed, integrations working
- ❌ **What's PLANNED** - Stored in `docs/master_plan.md` (task planning, not here)

**Exception:** The `decisions/` folder contains ADRs that can have status "Proposed" (discussing what to build) or "Accepted" (documenting decisions made).

## Domains

| Domain | Description |
|--------|-------------|
| [Architecture](architecture/index.md) | System design, database schema, API standards, tech stack |
| [Frontend](frontend/index.md) | Pages, components, UI standards, design system |
| [Backend](backend/index.md) | API endpoints, services, business logic |
| [Integrations](integrations/index.md) | Third-party services and integrations |
| [Security](security/index.md) | Authentication, authorization, security policies |
| [Decisions](decisions/index.md) | Architecture Decision Records (ADRs) |

## Quick Links

- [Changelog](CHANGELOG.md) - All updates to the vault
- [Tech Stack](architecture/tech-stack.md) - Technologies and frameworks used
- [Database Schema](architecture/database-schema.md) - Database tables and relationships
- [API Endpoints](backend/api-endpoints.md) - All REST/GraphQL endpoints

## How to Use This Vault

- **For developers**: Read the relevant domain docs before working on a task
- **For updates**: Update the specific domain file + add entry to CHANGELOG.md
- **For decisions**: Create an ADR in decisions/ and link from changelog
""".format(date=datetime.now().strftime("%Y-%m-%d"))

    (vault_dir / "INDEX.md").write_text(main_index)
    print(f"✓ Created INDEX.md")

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

    # Map of doc files to vault locations
    migrations = {
        "system_design.md": "architecture/system-design.md",
        "security_policy.md": "security/security-policy.md",
        "ui_standards.md": "frontend/ui-standards.md",
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

    # Create placeholder files
    placeholders = {
        "architecture/tech-stack.md": "# Tech Stack\n\n_Extract from codex.md_\n",
        "architecture/database-schema.md": "# Database Schema\n\n_Extract from codex.md_\n",
        "backend/api-endpoints.md": "# API Endpoints\n\n_Extract from codex.md_\n",
        "frontend/pages.md": "# Pages\n\n_Extract from codex.md_\n",
        "frontend/components.md": "# Components\n\n_Extract from codex.md_\n",
        "integrations/integrations.md": "# Integrations\n\n_Extract from codex.md_\n",
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
