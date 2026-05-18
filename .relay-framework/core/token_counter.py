"""
Token Counter Utility
=====================

Provides token counting for prompts to track context usage and prevent
exceeding model limits.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Cache the encoding to avoid reloading
_encoding = None


def _get_encoding():
    """Get or create the tiktoken encoding (cached)."""
    global _encoding
    if _encoding is None:
        try:
            import tiktoken
            # Use cl100k_base encoding (compatible with Claude/GPT-4)
            _encoding = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            logger.warning("tiktoken not installed, token counting disabled")
            return None
        except Exception as e:
            logger.warning(f"Failed to load tiktoken encoding: {e}")
            return None
    return _encoding


def count_tokens(text: str, model: str = "claude-sonnet-4-5") -> Optional[int]:
    """
    Count tokens in text using tiktoken.

    Args:
        text: Text to count tokens for
        model: Model name (not used currently, but available for future model-specific counting)

    Returns:
        Number of tokens, or None if tiktoken not available
    """
    encoding = _get_encoding()
    if encoding is None:
        return None

    try:
        return len(encoding.encode(text))
    except Exception as e:
        logger.warning(f"Failed to count tokens: {e}")
        return None


def estimate_tokens(text: str) -> int:
    """
    Estimate tokens using simple heuristic (if tiktoken unavailable).

    Uses rough estimate: 1 token ~= 4 characters for English text.

    Args:
        text: Text to estimate tokens for

    Returns:
        Estimated token count
    """
    # Try accurate counting first
    token_count = count_tokens(text)
    if token_count is not None:
        return token_count

    # Fallback to estimation
    return len(text) // 4


def count_prompt_components(
    system_prompt: str,
    vault_context: str = "",
    planning_context: str = "",
    task_history: str = "",
    task_description: str = ""
) -> dict:
    """
    Count tokens for each component of an agent prompt.

    Args:
        system_prompt: System prompt (role-specific)
        vault_context: Vault context (filtered implementation state)
        planning_context: Planning context (from docs)
        task_history: Task history log
        task_description: Task description

    Returns:
        Dictionary with token counts for each component
    """
    return {
        "system_prompt": estimate_tokens(system_prompt),
        "vault_context": estimate_tokens(vault_context),
        "planning_context": estimate_tokens(planning_context),
        "task_history": estimate_tokens(task_history),
        "task_description": estimate_tokens(task_description),
        "total": estimate_tokens(
            system_prompt + vault_context + planning_context +
            task_history + task_description
        )
    }


def format_token_report(token_counts: dict) -> str:
    """
    Format token counts into a readable report.

    Args:
        token_counts: Dictionary from count_prompt_components()

    Returns:
        Formatted string report
    """
    return (
        f"Prompt tokens: "
        f"system={token_counts['system_prompt']}, "
        f"vault={token_counts['vault_context']}, "
        f"planning={token_counts['planning_context']}, "
        f"history={token_counts['task_history']}, "
        f"task={token_counts['task_description']}, "
        f"total={token_counts['total']}"
    )
