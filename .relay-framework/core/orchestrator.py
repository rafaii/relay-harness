"""
Relay Orchestrator
==================

Main orchestrator for the Relay Framework.
Simplified for new architecture:
- SECTION 1 agents are launched directly via CLI (interview, architect, etc.)
- SECTION 2 execution is delegated to executor.py
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class RelayOrchestrator:
    """Main orchestrator for project execution."""

    def __init__(self, project_dir: Path, max_concurrency: int = 5):
        """
        Initialize orchestrator.

        Args:
            project_dir: Project directory
            max_concurrency: Maximum concurrent agents (default: 5)
        """
        self.project_dir = Path(project_dir)
        self.max_concurrency = max_concurrency
        logger.info(f"Orchestrator initialized: project_dir={project_dir}, max_concurrency={max_concurrency}")

    async def run_section_2_execution(self):
        """
        Run SECTION 2: Execution Loop.

        Delegates to executor.py for actual execution.
        This method manages the main execution loop with:
        - Developer agents spawning for pending tasks
        - QA gate for completed tasks
        - Security gate for QA-passed tasks
        - Browser verification for frontend tasks
        - Task status tracking
        """
        from core.executor import Executor
        from core.database import TaskDatabase
        from core.agent_spawner import AgentSpawner

        # Initialize components
        db = TaskDatabase(self.project_dir)
        spawner = AgentSpawner(
            project_dir=self.project_dir,
            db=db,
            max_concurrency=self.max_concurrency
        )

        # Create executor
        executor = Executor(
            project_dir=self.project_dir,
            db=db,
            spawner=spawner,
            max_concurrency=self.max_concurrency
        )

        logger.info("Starting SECTION 2: Execution Loop")

        try:
            await executor.execute()
            logger.info("Execution completed successfully")
        except KeyboardInterrupt:
            logger.info("Execution interrupted by user")
            executor.shutdown()
            raise
        except Exception as e:
            logger.error(f"Execution failed: {e}", exc_info=True)
            executor.shutdown()
            raise


if __name__ == "__main__":
    # Test the orchestrator
    import sys
    if len(sys.argv) > 1:
        project_dir = Path(sys.argv[1])
    else:
        project_dir = Path.cwd()

    logging.basicConfig(level=logging.INFO)
    orchestrator = RelayOrchestrator(project_dir)
    asyncio.run(orchestrator.run_section_2_execution())
