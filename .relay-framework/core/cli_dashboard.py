"""
CLI Dashboard for real-time task status display.
"""

import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

# Try to import rich for better formatting
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.live import Live
    from rich.layout import Layout
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


@dataclass
class AgentDisplay:
    """Data for displaying an active agent."""
    task_id: str
    task_title: str
    agent_name: str  # Human-readable name like "Stacey", "Phoenix"
    agent_type: str  # Type like "Frontend Developer", "QA", "Security"
    status: str  # Current workflow status
    start_time: datetime


class CLIDashboard:
    """
    Real-time CLI dashboard for task execution.

    Shows:
    - Overall statistics
    - Active agents with their tasks
    - Tasks waiting to be picked up
    """

    def __init__(self, use_rich: bool = True):
        """
        Initialize dashboard.

        Args:
            use_rich: Use rich library for formatting (if available)
        """
        self.use_rich = use_rich and RICH_AVAILABLE
        self.console = Console() if self.use_rich else None
        self.live = None

    def start(self):
        """Start the live dashboard display."""
        if self.use_rich and self.console and RICH_AVAILABLE:
            try:
                self.live = Live(console=self.console, refresh_per_second=1)
                self.live.start()
            except Exception:
                # If rich fails, fall back to basic mode
                self.use_rich = False
                self.live = None

    def stop(self):
        """Stop the live dashboard display."""
        if self.live:
            self.live.stop()
            self.live = None

    def update(
        self,
        stats: Dict,
        active_agents: List[AgentDisplay],
        waiting_tasks: List[tuple],
        max_concurrency: int = 5,
        recent_completions: Optional[List[tuple]] = None,
        elapsed_time: Optional[float] = None,
        avg_task_time: Optional[float] = None
    ):
        """
        Update the dashboard with current state.

        Args:
            stats: Statistics dictionary
            active_agents: List of AgentDisplay objects
            waiting_tasks: List of (task_id, title, role) tuples for tasks waiting
            max_concurrency: Maximum concurrent agents
            recent_completions: List of (task_id, title, completion_time) tuples for recently completed tasks
            elapsed_time: Total elapsed time in seconds
            avg_task_time: Average task completion time in seconds
        """
        if self.use_rich:
            self._update_rich(stats, active_agents, waiting_tasks, max_concurrency, recent_completions, elapsed_time, avg_task_time)
        else:
            self._update_basic(stats, active_agents, waiting_tasks, max_concurrency, recent_completions, elapsed_time, avg_task_time)

    def _update_rich(
        self,
        stats: Dict,
        active_agents: List[AgentDisplay],
        waiting_tasks: List[tuple],
        max_concurrency: int = 5,
        recent_completions: Optional[List[tuple]] = None,
        elapsed_time: Optional[float] = None,
        avg_task_time: Optional[float] = None
    ):
        """Update using rich library."""
        if not RICH_AVAILABLE:
            # Fallback to basic display
            self._update_basic(stats, active_agents, waiting_tasks, max_concurrency, recent_completions, elapsed_time, avg_task_time)
            return

        layout = Layout()

        # Create statistics panel
        stats_content = self._create_stats_display(stats, elapsed_time, avg_task_time, max_concurrency)
        stats_panel = Panel(
            stats_content,
            title="[bold cyan]Task Statistics[/bold cyan]",
            border_style="cyan"
        )

        # Create active agents panel
        agents_content = self._create_agents_table(active_agents)
        agents_panel = Panel(
            agents_content,
            title="[bold yellow]Active Agents[/bold yellow]",
            border_style="yellow"
        )

        # Create waiting tasks panel
        waiting_content = self._create_waiting_table(waiting_tasks)
        waiting_panel = Panel(
            waiting_content,
            title="[bold green]Tasks Ready to Start[/bold green]",
            border_style="green"
        )

        # Combine all panels
        layout.split_column(
            Layout(stats_panel, size=8),
            Layout(agents_panel, size=12),
            Layout(waiting_panel)
        )

        if self.live:
            self.live.update(layout)

    def _create_stats_display(self, stats: Dict, elapsed_time: Optional[float] = None,
                                  avg_task_time: Optional[float] = None, max_concurrency: int = 5) -> str:
        """Create statistics display."""
        total = stats.get('total', 0)
        completed = stats.get('completed', 0)
        progress = (completed / total * 100) if total > 0 else 0

        in_development = stats.get('in_development', 0)
        todo = stats.get('todo', 0)
        ready_for_qa = stats.get('ready_for_qa', 0)
        in_qa = stats.get('in_qa', 0)
        qa_failed = stats.get('qa_failed', 0)
        ready_for_security = stats.get('ready_for_security', 0)
        in_security = stats.get('in_security', 0)
        security_failed = stats.get('security_failed', 0)
        failed = stats.get('failed', 0)

        lines = [
            f"[bold]Total Tasks:[/bold] {total}",
            f"[bold]Progress:[/bold] {progress:.1f}%",
            "",
            f"🔧 Development: [yellow]{in_development}[/yellow]  │  ⏸️  Pending: {todo} │ ✅ Completed: [green]{completed}[/green]",
        ]

        if failed > 0:
            lines[-1] += f"  │  ⚠️  Failed: [red]{failed}[/red]"

        lines.extend([
            "",
            f"🧪 Waiting QA: {ready_for_qa}   │  🧪🔍 QA Testing: [blue]{in_qa}[/blue]  │ 🧪❌ QA Fixing: [red]{qa_failed}[/red]",
            f"🔐 Waiting Security: {ready_for_security} │  🔐🔍 Security Testing: [magenta]{in_security}[/magenta]  │ 🔐❌ Security Fixing: [red]{security_failed}[/red]",
        ])

        # Add time information if available
        if elapsed_time is not None:
            elapsed_minutes = elapsed_time / 60
            lines.append("")
            lines.append(f"[bold]Elapsed Time:[/bold] {elapsed_minutes:.1f}m")

            # Calculate ETA
            if avg_task_time and completed > 0:
                remaining_tasks = total - completed
                estimated_remaining_seconds = remaining_tasks * avg_task_time / max(1, max_concurrency)
                eta_minutes = estimated_remaining_seconds / 60

                if eta_minutes < 1:
                    eta_str = "< 1 minute"
                elif eta_minutes < 60:
                    eta_str = f"~{int(eta_minutes)} minutes"
                else:
                    eta_hours = eta_minutes / 60
                    eta_str = f"~{eta_hours:.1f} hours"

                lines.append(f"[bold]ETA:[/bold] {eta_str}")

        return "\n".join(lines)

    def _create_agents_table(self, active_agents: List[AgentDisplay]):
        """Create table of active agents."""
        if not RICH_AVAILABLE:
            return "Rich library not available"

        table = Table(show_header=True, header_style="bold", show_lines=False)
        table.add_column("Agent", width=40)
        table.add_column("Task", width=50)

        if not active_agents:
            table.add_row("[dim]No active agents[/dim]", "")
            return table

        for agent in active_agents:
            # Calculate runtime
            runtime = datetime.now() - agent.start_time
            elapsed = runtime.total_seconds()
            elapsed_min = elapsed / 60

            # Format elapsed time
            if elapsed_min < 1:
                time_str = f"{elapsed:.0f}s"
            else:
                time_str = f"{elapsed_min:.1f}m"

            # Get workflow status icon
            status_icon = self._get_workflow_status_icon(agent.status)

            # Format agent display
            agent_display = f"{status_icon} {agent.agent_name} ({agent.agent_type})    {time_str}"

            # Format task display
            task_display = f"↳ {agent.task_id}: {agent.task_title[:40]}"

            table.add_row(agent_display, task_display)

        return table

    def _create_waiting_table(self, waiting_tasks: List[tuple]):
        """Create table of tasks waiting to be picked up."""
        if not RICH_AVAILABLE:
            return "Rich library not available"

        table = Table(show_header=True, header_style="bold")
        table.add_column("Task ID", width=15)
        table.add_column("Title", width=40)
        table.add_column("Role", width=20)

        if not waiting_tasks:
            table.add_row("", "[dim]No tasks waiting[/dim]", "")
            return table

        # Limit to first 10 waiting tasks
        for task_id, title, role in waiting_tasks[:10]:
            # Truncate title if too long
            title_display = title[:37] + "..." if len(title) > 40 else title
            table.add_row(task_id, title_display, role)

        if len(waiting_tasks) > 10:
            table.add_row("", f"[dim]...and {len(waiting_tasks) - 10} more[/dim]", "")

        return table

    def _update_basic(
        self,
        stats: Dict,
        active_agents: List[AgentDisplay],
        waiting_tasks: List[tuple],
        max_concurrency: int = 5,
        recent_completions: Optional[List[tuple]] = None,
        elapsed_time: Optional[float] = None,
        avg_task_time: Optional[float] = None
    ):
        """Update using basic terminal output with enhanced formatting."""
        # Clear screen for better readability
        print("\033[2J\033[H", end="")

        print("\n" + "=" * 80)
        print("🎯 RELAY FRAMEWORK - EXECUTION DASHBOARD")
        print("=" * 80)

        # Print overall progress with visual progress bar
        total = stats.get('total', 0)
        completed = stats.get('completed', 0)
        in_development = stats.get('in_development', 0)
        in_qa = stats.get('in_qa', 0)
        in_security = stats.get('in_security', 0)
        ready_for_qa = stats.get('ready_for_qa', 0)
        ready_for_security = stats.get('ready_for_security', 0)
        todo = stats.get('todo', 0)
        qa_failed = stats.get('qa_failed', 0)
        qa_fixing = stats.get('qa_fixing', 0)
        security_failed = stats.get('security_failed', 0)
        security_fixing = stats.get('security_fixing', 0)

        print(f"\n📊 Overall Progress: {completed}/{total} tasks completed")
        if total > 0:
            progress_pct = (completed / total) * 100
            bar_length = 50
            filled = int(bar_length * completed / total)
            bar = "█" * filled + "▒" * (bar_length - filled)
            print(f"\n   [{bar}] {progress_pct:.1f}%")
        print()

        # Status breakdown with detailed workflow indicators
        print("   📊 Workflow Status:")
        print()

        # Combined status line
        status_line = f"   🔧 Development: {in_development:>2}  │  ⏸️  Pending: {todo:>3} │ ✅ Completed: {completed:>3}"
        if stats.get('failed', 0) > 0:
            status_line += f"  │  ⚠️  Failed: {stats.get('failed', 0):>2}"
        print(status_line)

        # QA workflow line
        qa_line = f"   🧪 Waiting QA: {ready_for_qa:>2}   │  🧪🔍 QA Testing: {in_qa:>2}  │ 🧪🔧 QA Fixing: {qa_fixing:>2}"
        print(qa_line)

        # Security workflow line
        security_line = f"   🔐 Waiting Security: {ready_for_security:>2} │  🔐🔍 Security Testing: {in_security:>2}  │ 🔐🔧 Security Fixing: {security_fixing:>2}"
        print(security_line)
        print()

        # Active agents with status icons
        print(f"\n🤖 Active Agents ({len(active_agents)}/{max_concurrency}):")

        if active_agents:
            for agent in active_agents[:8]:  # Show up to 8 agents
                runtime = datetime.now() - agent.start_time
                elapsed = runtime.total_seconds()
                elapsed_min = elapsed / 60

                # Format elapsed time
                if elapsed_min < 1:
                    time_str = f"{elapsed:.0f}s"
                else:
                    time_str = f"{elapsed_min:.1f}m"

                # Get status icon based on current workflow state
                status_icon = self._get_workflow_status_icon(agent.status)

                # Display agent with status icon
                print(f"   {status_icon} {agent.agent_name} ({agent.agent_type})    {time_str:>6}")
                print(f"     ↳ {agent.task_id}: {agent.task_title[:50]}")

            if len(active_agents) > 8:
                print(f"   ... and {len(active_agents) - 8} more agents")
        else:
            print("   (none - waiting for ready tasks)")

        # Next ready tasks preview
        if waiting_tasks:
            print(f"\n📋 Next Ready Tasks ({len(waiting_tasks)} available):")
            for i, (task_id, title, role) in enumerate(waiting_tasks[:5], 1):
                print(f"   {i}. [{role:>20}] {task_id}: {title[:40]}")

        # Time information with ETA
        if elapsed_time is not None:
            elapsed_minutes = elapsed_time / 60
            time_info = f"\n   ⏱️  Elapsed: {elapsed_minutes:.1f}m"

            # Calculate ETA if we have average task time
            if avg_task_time and completed > 0:
                remaining_tasks = total - completed
                estimated_remaining_seconds = remaining_tasks * avg_task_time / max(1, max_concurrency)
                eta_minutes = estimated_remaining_seconds / 60

                if eta_minutes < 1:
                    eta_str = "< 1 minute"
                elif eta_minutes < 60:
                    eta_str = f"~{int(eta_minutes)} minutes"
                else:
                    eta_hours = eta_minutes / 60
                    eta_str = f"~{eta_hours:.1f} hours"

                time_info += f"  │  ETA: {eta_str}"

            print(time_info)

        # Recent completions
        if recent_completions and len(recent_completions) > 0:
            print(f"\n✅ Recent Completions:")
            for task_id, title, completion_time in recent_completions[:3]:
                time_str = f"{completion_time:.1f}m" if completion_time > 0 else "?"
                print(f"   ✓ {task_id}: {title[:50]} ({time_str})")

        # Footer
        print("\n" + "-" * 80)
        print("Press Ctrl+C to stop (execution can be resumed later)")
        print("-" * 80)

    def _get_status_icon(self, status: str) -> str:
        """Get rich status icon."""
        icons = {
            'in_development': '🔧',
            'in_qa': '🧪🔍',
            'qa_failed': '🧪❌',
            'qa_fixing': '🧪🔨',
            'in_security': '🔐🔍',
            'security_failed': '🔐❌',
            'security_fixing': '🔐🔨',
            'ready_for_qa': '🧪⏸️',
            'ready_for_security': '🔐⏸️',
            'done': '✅',
            'failed': '❌',
            'todo': '⏸️'
        }
        return icons.get(status, '🔄')

    def _get_workflow_status_icon(self, status: str) -> str:
        """Get workflow status icon for agent display."""
        icons = {
            'in_development': '🔧',
            'in_qa': '🧪🔍',
            'qa_failed': '🧪❌',
            'qa_fixing': '🧪🔨',
            'in_security': '🔐🔍',
            'security_failed': '🔐❌',
            'security_fixing': '🔐🔨',
            'ready_for_qa': '🧪⏸️',
            'ready_for_security': '🔐⏸️',
            'done': '✅',
            'failed': '❌',
            'todo': '⏸️'
        }
        return icons.get(status, '🔄')

    def _get_status_icon_basic(self, status: str) -> str:
        """Get basic status icon."""
        icons = {
            'in_development': '[DEV]',
            'in_qa': '[QA ]',
            'in_security': '[SEC]',
            'ready_for_qa': '[RDY]',
            'ready_for_security': '[RDY]',
            'done': '[DON]',
            'failed': '[ERR]',
            'todo': '[TODO]',
            'qa_failed': '[FAIL]',
            'security_failed': '[FAIL]'
        }
        return icons.get(status, '[RUN]')

    def _format_timedelta(self, td: timedelta) -> str:
        """Format timedelta as HH:MM:SS."""
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
