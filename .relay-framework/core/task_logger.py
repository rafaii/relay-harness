"""
Task Logger
===========

Creates and maintains detailed markdown log files for each task.
Provides a complete audit trail of the entire task lifecycle.
"""

from pathlib import Path
from datetime import datetime
from typing import Optional


class TaskLogger:
    """
    Manages detailed markdown log files for tasks.

    Each task gets its own .md file in .relay/logs/ that tracks:
    - Task description and requirements
    - All development work
    - QA testing results
    - Security scan results
    - Complete history of fixes and retests
    """

    def __init__(self, project_dir: Path):
        """
        Initialize task logger.

        Args:
            project_dir: Project directory containing .relay folder
        """
        self.project_dir = Path(project_dir)
        self.logs_dir = self.project_dir / ".relay" / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _get_task_log_path(self, task_id: str) -> Path:
        """Get path to task log markdown file."""
        return self.logs_dir / f"{task_id}.md"

    def _ensure_task_header(self, task_id: str, task_title: str, task_description: str):
        """
        Ensure task log file exists with header.
        Creates file if it doesn't exist.
        """
        log_path = self._get_task_log_path(task_id)

        if not log_path.exists():
            header = f"""# Task {task_id}: {task_title}

## 📋 Task Description

{task_description}

---

## 📝 Task Log

"""
            log_path.write_text(header)

    def log_development_start(
        self,
        task_id: str,
        task_title: str,
        task_description: str,
        agent_id: str,
        agent_name: str
    ):
        """Log when development starts on a task."""
        self._ensure_task_header(task_id, task_title, task_description)

        log_path = self._get_task_log_path(task_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = f"""### 🔨 Development Started
**Time:** {timestamp}
**Agent:** {agent_name} ({agent_id})
**Status:** Development in progress

"""

        with open(log_path, 'a') as f:
            f.write(entry)

    def log_development_complete(
        self,
        task_id: str,
        agent_id: str,
        agent_name: str,
        work_summary: str,
        files_modified: Optional[list] = None
    ):
        """Log when development work is completed."""
        log_path = self._get_task_log_path(task_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        files_section = ""
        if files_modified:
            files_list = "\n".join(f"  - `{f}`" for f in files_modified)
            files_section = f"\n\n**Files Modified:**\n{files_list}"

        entry = f"""### ✅ Development Completed
**Time:** {timestamp}
**Agent:** {agent_name} ({agent_id})
**Status:** Ready for QA

**Work Summary:**
{work_summary}{files_section}

---

"""

        with open(log_path, 'a') as f:
            f.write(entry)

    def log_qa_start(
        self,
        task_id: str,
        agent_id: str,
        agent_name: str
    ):
        """Log when QA testing starts."""
        log_path = self._get_task_log_path(task_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = f"""### 🔍 QA Testing Started
**Time:** {timestamp}
**Agent:** {agent_name} ({agent_id})
**Status:** QA in progress

"""

        with open(log_path, 'a') as f:
            f.write(entry)

    def log_qa_result(
        self,
        task_id: str,
        agent_id: str,
        agent_name: str,
        passed: bool,
        test_summary: str,
        issues_found: Optional[list] = None
    ):
        """Log QA testing results."""
        log_path = self._get_task_log_path(task_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        status_emoji = "✅" if passed else "❌"
        status_text = "PASSED" if passed else "FAILED"

        issues_section = ""
        if not passed and issues_found:
            issues_list = "\n".join(f"  {i+1}. {issue}" for i, issue in enumerate(issues_found))
            issues_section = f"\n\n**Issues Found:**\n{issues_list}"

        entry = f"""### {status_emoji} QA Testing {status_text}
**Time:** {timestamp}
**Agent:** {agent_name} ({agent_id})
**Status:** {'Ready for Security' if passed else 'Needs Developer Fixes'}

**Test Summary:**
{test_summary}{issues_section}

---

"""

        with open(log_path, 'a') as f:
            f.write(entry)

    def log_qa_fix_start(
        self,
        task_id: str,
        agent_id: str,
        agent_name: str,
        fixing_issues: list
    ):
        """Log when developer starts fixing QA issues."""
        log_path = self._get_task_log_path(task_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        issues_list = "\n".join(f"  - {issue}" for issue in fixing_issues)

        entry = f"""### 🔧 Fixing QA Issues
**Time:** {timestamp}
**Agent:** {agent_name} ({agent_id})
**Status:** Fixing issues

**Issues Being Fixed:**
{issues_list}

"""

        with open(log_path, 'a') as f:
            f.write(entry)

    def log_security_start(
        self,
        task_id: str,
        agent_id: str,
        agent_name: str
    ):
        """Log when security scanning starts."""
        log_path = self._get_task_log_path(task_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = f"""### 🔒 Security Scan Started
**Time:** {timestamp}
**Agent:** {agent_name} ({agent_id})
**Status:** Security scan in progress

"""

        with open(log_path, 'a') as f:
            f.write(entry)

    def log_security_result(
        self,
        task_id: str,
        agent_id: str,
        agent_name: str,
        passed: bool,
        scan_summary: str,
        vulnerabilities_found: Optional[list] = None
    ):
        """Log security scan results."""
        log_path = self._get_task_log_path(task_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        status_emoji = "✅" if passed else "🚨"
        status_text = "PASSED" if passed else "FAILED"

        vuln_section = ""
        if not passed and vulnerabilities_found:
            vuln_list = "\n".join(f"  - **{vuln['severity']}**: {vuln['description']}" for vuln in vulnerabilities_found)
            vuln_section = f"\n\n**Vulnerabilities Found:**\n{vuln_list}"

        entry = f"""### {status_emoji} Security Scan {status_text}
**Time:** {timestamp}
**Agent:** {agent_name} ({agent_id})
**Status:** {'✅ TASK COMPLETE' if passed else 'Needs Developer Fixes'}

**Scan Summary:**
{scan_summary}{vuln_section}

---

"""

        with open(log_path, 'a') as f:
            f.write(entry)

    def log_security_fix_start(
        self,
        task_id: str,
        agent_id: str,
        agent_name: str,
        fixing_vulnerabilities: list
    ):
        """Log when developer starts fixing security issues."""
        log_path = self._get_task_log_path(task_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        vuln_list = "\n".join(f"  - {vuln}" for vuln in fixing_vulnerabilities)

        entry = f"""### 🔐 Fixing Security Issues
**Time:** {timestamp}
**Agent:** {agent_name} ({agent_id})
**Status:** Fixing vulnerabilities

**Security Issues Being Fixed:**
{vuln_list}

"""

        with open(log_path, 'a') as f:
            f.write(entry)

    def log_task_complete(
        self,
        task_id: str
    ):
        """Log final task completion."""
        log_path = self._get_task_log_path(task_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = f"""
---

## 🎉 Task Completed Successfully

**Completion Time:** {timestamp}
**Status:** ✅ DONE

All requirements met. Task passed development, QA testing, and security scanning.

"""

        with open(log_path, 'a') as f:
            f.write(entry)

    def get_task_log(self, task_id: str) -> Optional[str]:
        """
        Get the complete task log.

        Args:
            task_id: Task ID

        Returns:
            Full task log content or None if file doesn't exist
        """
        log_path = self._get_task_log_path(task_id)

        if log_path.exists():
            return log_path.read_text()

        return None
