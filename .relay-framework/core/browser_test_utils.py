"""
Browser Testing Utilities for Relay Framework
==============================================

Provides browser testing capabilities for agents to verify frontend tasks
using Playwright. Supports headless browser automation for UI verification.

Usage in agent code:
    from core.browser_test_utils import BrowserTestRunner, TestResult

    runner = BrowserTestRunner(project_dir=Path("."))
    results = await runner.run_test_steps([
        {"action": "navigate", "url": "http://localhost:3000"},
        {"action": "check_title", "operator": "contains", "value": "My App"},
        {"action": "check_element", "selector": "#login-button", "check": "visible"},
        {"action": "click", "selector": "#login-button"},
        {"action": "screenshot", "name": "after_click"},
        {"action": "check_url", "operator": "contains", "value": "/dashboard"}
    ])
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Result of a browser test step."""
    success: bool
    message: str
    screenshot_path: Optional[Path] = None
    timestamp: Optional[datetime] = None


class BrowserTestRunner:
    """
    Browser test runner using Playwright for frontend verification.

    Allows developer agents to self-verify UI before submitting to QA gate.
    Supports headless Chrome automation with screenshot capture.
    """

    def __init__(
        self,
        project_dir: Path,
        headless: bool = True,
        timeout: int = 30000
    ):
        """
        Initialize browser test runner.

        Args:
            project_dir: Project root directory
            headless: Run browser in headless mode (default: True)
            timeout: Default timeout for operations in milliseconds (default: 30000)
        """
        self.project_dir = Path(project_dir)
        self.screenshots_dir = self.project_dir / ".relay" / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.timeout = timeout
        self.browser = None
        self.context = None
        self.page = None

    async def initialize(self):
        """Initialize Playwright browser instance."""
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self.browser = await self._playwright.chromium.launch(headless=self.headless)
            self.context = await self.browser.new_context(
                viewport={'width': 1280, 'height': 720}
            )
            self.page = await self.context.new_page()
            self.page.set_default_timeout(self.timeout)

            logger.info(f"Browser initialized (headless={self.headless})")

        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            raise

    async def cleanup(self):
        """Close browser and cleanup resources."""
        if self.browser:
            await self.browser.close()
            logger.info("Browser closed")
        if hasattr(self, '_playwright'):
            await self._playwright.stop()

    async def run_test_steps(self, steps: List[Dict]) -> List[TestResult]:
        """
        Execute a sequence of browser test steps.

        Args:
            steps: List of step dictionaries with format:
                {"action": "navigate", "url": "http://..."}
                {"action": "check_title", "operator": "contains", "value": "..."}
                {"action": "check_element", "selector": "#id", "check": "visible|exists"}
                {"action": "click", "selector": "#id"}
                {"action": "fill", "selector": "#id", "value": "text"}
                {"action": "check_url", "operator": "contains|equals", "value": "..."}
                {"action": "wait", "milliseconds": 1000}
                {"action": "screenshot", "name": "step_name"}

        Returns:
            List of TestResult objects
        """
        results = []

        # Initialize browser if not already done
        if not self.page:
            await self.initialize()

        for i, step in enumerate(steps):
            try:
                result = await self._execute_step(step)
                results.append(result)

                # Stop on first failure
                if not result.success:
                    logger.warning(f"Step {i+1} failed: {result.message}")
                    break

            except Exception as e:
                logger.error(f"Step {i+1} error: {e}", exc_info=True)
                results.append(TestResult(
                    success=False,
                    message=f"Step error: {e}",
                    timestamp=datetime.now()
                ))
                break

        return results

    async def _execute_step(self, step: Dict) -> TestResult:
        """Execute a single test step."""
        action = step.get("action")
        timestamp = datetime.now()

        try:
            if action == "navigate":
                url = step["url"]
                logger.info(f"Navigating to {url}")
                await self.page.goto(url, wait_until="networkidle")
                return TestResult(
                    success=True,
                    message=f"Successfully loaded {url}",
                    timestamp=timestamp
                )

            elif action == "check_title":
                operator = step["operator"]  # "contains" or "equals"
                expected = step["value"]
                actual = await self.page.title()

                if operator == "contains":
                    success = expected.lower() in actual.lower()
                elif operator == "equals":
                    success = expected == actual
                else:
                    return TestResult(
                        success=False,
                        message=f"Unknown operator: {operator}",
                        timestamp=timestamp
                    )

                return TestResult(
                    success=success,
                    message=f"Title '{actual}' {operator} '{expected}': {success}",
                    timestamp=timestamp
                )

            elif action == "check_element":
                selector = step["selector"]
                check_type = step["check"]  # "visible" or "exists"

                if check_type == "visible":
                    element = self.page.locator(selector)
                    is_visible = await element.is_visible()
                    return TestResult(
                        success=is_visible,
                        message=f"Element '{selector}' visible: {is_visible}",
                        timestamp=timestamp
                    )
                elif check_type == "exists":
                    count = await self.page.locator(selector).count()
                    success = count > 0
                    return TestResult(
                        success=success,
                        message=f"Element '{selector}' exists: {success} (count: {count})",
                        timestamp=timestamp
                    )
                else:
                    return TestResult(
                        success=False,
                        message=f"Unknown check type: {check_type}",
                        timestamp=timestamp
                    )

            elif action == "click":
                selector = step["selector"]
                await self.page.click(selector)
                await self.page.wait_for_load_state("networkidle")
                return TestResult(
                    success=True,
                    message=f"Clicked element '{selector}'",
                    timestamp=timestamp
                )

            elif action == "fill":
                selector = step["selector"]
                value = step["value"]
                await self.page.fill(selector, value)
                return TestResult(
                    success=True,
                    message=f"Filled '{selector}' with value",
                    timestamp=timestamp
                )

            elif action == "check_url":
                operator = step["operator"]  # "contains" or "equals"
                expected = step["value"]
                actual = self.page.url

                if operator == "contains":
                    success = expected in actual
                elif operator == "equals":
                    success = expected == actual
                else:
                    return TestResult(
                        success=False,
                        message=f"Unknown operator: {operator}",
                        timestamp=timestamp
                    )

                return TestResult(
                    success=success,
                    message=f"URL '{actual}' {operator} '{expected}': {success}",
                    timestamp=timestamp
                )

            elif action == "wait":
                milliseconds = step["milliseconds"]
                await asyncio.sleep(milliseconds / 1000)
                return TestResult(
                    success=True,
                    message=f"Waited {milliseconds}ms",
                    timestamp=timestamp
                )

            elif action == "screenshot":
                name = step.get("name", "screenshot")
                screenshot_path = self.screenshots_dir / f"{name}_{timestamp.strftime('%Y%m%d_%H%M%S')}.png"
                await self.page.screenshot(path=str(screenshot_path))
                return TestResult(
                    success=True,
                    message=f"Screenshot saved",
                    screenshot_path=screenshot_path,
                    timestamp=timestamp
                )

            else:
                return TestResult(
                    success=False,
                    message=f"Unknown action: {action}",
                    timestamp=timestamp
                )

        except Exception as e:
            logger.error(f"Step '{action}' failed: {e}")
            return TestResult(
                success=False,
                message=f"Error: {e}",
                timestamp=timestamp
            )

    def run_test_steps_sync(self, steps: List[Dict]) -> List[TestResult]:
        """
        Synchronous wrapper for run_test_steps.

        Args:
            steps: List of test step dictionaries

        Returns:
            List of TestResult objects
        """
        return asyncio.run(self._run_with_cleanup(steps))

    async def _run_with_cleanup(self, steps: List[Dict]) -> List[TestResult]:
        """Run tests and ensure cleanup happens."""
        try:
            results = await self.run_test_steps(steps)
            return results
        finally:
            await self.cleanup()


# Convenience function for one-off tests
async def run_browser_test(
    project_dir: Path,
    steps: List[Dict],
    headless: bool = True
) -> List[TestResult]:
    """
    Convenience function to run a browser test with automatic cleanup.

    Args:
        project_dir: Project root directory
        steps: List of test step dictionaries
        headless: Run browser in headless mode

    Returns:
        List of TestResult objects
    """
    runner = BrowserTestRunner(project_dir, headless=headless)
    try:
        await runner.initialize()
        results = await runner.run_test_steps(steps)
        return results
    finally:
        await runner.cleanup()


def run_browser_test_sync(
    project_dir: Path,
    steps: List[Dict],
    headless: bool = True
) -> List[TestResult]:
    """Synchronous wrapper for run_browser_test."""
    return asyncio.run(run_browser_test(project_dir, steps, headless))
