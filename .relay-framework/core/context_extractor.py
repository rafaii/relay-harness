"""
Context Extractor
=================

Extracts relevant sections from planning documents based on task context.
Simpler alternative to vector DB - uses markdown section parsing and keyword matching.
"""

import re
from pathlib import Path
from typing import List, Dict, Tuple


class ContextExtractor:
    """
    Extracts relevant sections from planning documents.

    Instead of loading entire files, parses markdown headers and returns
    only sections that match task keywords.
    """

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.docs_dir = project_dir / "docs"

    def get_relevant_context(
        self,
        task_description: str,
        task_role: str,
        max_sections: int = 5
    ) -> str:
        """
        Extract relevant sections from planning docs.

        Args:
            task_description: Task description text
            task_role: Task role (frontend_developer, backend_developer, etc.)
            max_sections: Maximum sections to return per document

        Returns:
            Formatted string with relevant sections
        """
        # Extract keywords from task description
        keywords = self._extract_keywords(task_description)

        context_parts = []

        # Always include system_design.md sections
        system_design = self.docs_dir / "system_design.md"
        if system_design.exists():
            sections = self._get_relevant_sections(
                system_design,
                keywords,
                max_sections=max_sections
            )
            if sections:
                context_parts.append("## docs/system_design.md\n")
                context_parts.extend(sections)

        # Include security_policy.md for security-sensitive tasks
        if self._is_security_sensitive(task_description):
            security_policy = self.docs_dir / "security_policy.md"
            if security_policy.exists():
                sections = self._get_relevant_sections(
                    security_policy,
                    keywords,
                    max_sections=3
                )
                if sections:
                    context_parts.append("\n## docs/security_policy.md\n")
                    context_parts.extend(sections)

        # Include ui_standards.md for frontend tasks
        if 'frontend' in task_role.lower():
            ui_standards = self.docs_dir / "ui_standards.md"
            if ui_standards.exists():
                sections = self._get_relevant_sections(
                    ui_standards,
                    keywords,
                    max_sections=4
                )
                if sections:
                    context_parts.append("\n## docs/ui_standards.md\n")
                    context_parts.extend(sections)

        # If no sections matched, return a summary note
        if not context_parts:
            return (
                "**Note:** No specific sections matched task keywords. "
                "Read full planning docs if needed:\n"
                f"  - {system_design}\n"
                f"  - {security_policy if self._is_security_sensitive(task_description) else ''}\n"
                f"  - {ui_standards if 'frontend' in task_role.lower() else ''}\n"
            )

        return "\n".join(context_parts)

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract relevant keywords from task description."""
        # Convert to lowercase and split
        words = re.findall(r'\b\w+\b', text.lower())

        # Filter out common stop words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at',
            'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'are',
            'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
            'do', 'does', 'did', 'will', 'would', 'should', 'could',
            'this', 'that', 'these', 'those', 'task', 'should', 'must'
        }

        keywords = [w for w in words if w not in stop_words and len(w) > 3]

        # Return unique keywords, most frequent first
        from collections import Counter
        counter = Counter(keywords)
        return [word for word, _ in counter.most_common(10)]

    def _get_relevant_sections(
        self,
        doc_path: Path,
        keywords: List[str],
        max_sections: int = 5
    ) -> List[str]:
        """
        Extract sections from markdown file that match keywords.

        Args:
            doc_path: Path to markdown file
            keywords: List of keywords to match
            max_sections: Maximum sections to return

        Returns:
            List of section strings (including headers)
        """
        try:
            content = doc_path.read_text()
        except Exception:
            return []

        # Parse into sections
        sections = self._parse_sections(content)

        # Score sections by keyword matches
        scored_sections = []
        for section in sections:
            score = self._score_section(section, keywords)
            if score > 0:
                scored_sections.append((score, section))

        # Sort by score (descending) and take top N
        scored_sections.sort(reverse=True, key=lambda x: x[0])
        return [section for _, section in scored_sections[:max_sections]]

    def _parse_sections(self, content: str) -> List[str]:
        """
        Parse markdown into sections by headers.

        Returns list of section strings (header + content).
        """
        lines = content.split('\n')
        sections = []
        current_section = []
        current_level = 0

        for line in lines:
            # Check if line is a header
            header_match = re.match(r'^(#{1,6})\s+(.+)$', line)

            if header_match:
                level = len(header_match.group(1))

                # Save previous section if exists
                if current_section and current_level > 0:
                    sections.append('\n'.join(current_section))

                # Start new section
                current_section = [line]
                current_level = level
            else:
                # Add line to current section
                if current_section:
                    current_section.append(line)

        # Save last section
        if current_section:
            sections.append('\n'.join(current_section))

        return sections

    def _score_section(self, section: str, keywords: List[str]) -> int:
        """
        Score section by keyword matches.

        Args:
            section: Section text
            keywords: Keywords to match

        Returns:
            Match score (higher = more relevant)
        """
        section_lower = section.lower()
        score = 0

        for keyword in keywords:
            # Count occurrences of keyword
            count = section_lower.count(keyword)
            score += count

            # Bonus if keyword in header
            header_line = section.split('\n')[0].lower()
            if keyword in header_line:
                score += 3

        return score

    def _is_security_sensitive(self, task_description: str) -> bool:
        """Check if task is security-sensitive."""
        security_keywords = [
            'auth', 'login', 'password', 'encrypt', 'permission',
            'token', 'session', 'credential', 'security', 'vulnerability',
            'sanitize', 'validate', 'escape', 'injection'
        ]

        desc_lower = task_description.lower()
        return any(kw in desc_lower for kw in security_keywords)


def extract_relevant_context(
    project_dir: Path,
    task_description: str,
    task_role: str
) -> str:
    """
    Convenience function to extract relevant context.

    Args:
        project_dir: Project directory
        task_description: Task description
        task_role: Task role

    Returns:
        Formatted context string
    """
    extractor = ContextExtractor(project_dir)
    return extractor.get_relevant_context(task_description, task_role)
