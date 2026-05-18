"""
Shared Keyword Utilities
========================

Provides consistent keyword extraction and normalization across
context_extractor and vault_filter modules.
"""

import re
from typing import List, Set
from collections import Counter


# Common English stop words to filter out
STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "about", "into", "through", "during",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "should", "could", "may", "might",
    "must", "can", "this", "that", "these", "those", "i", "you", "he", "she",
    "it", "we", "they", "what", "which", "who", "when", "where", "why", "how",
    "all", "each", "every", "both", "few", "more", "most", "other", "some",
    "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too",
    "very", "just", "now", "need", "create", "update", "add", "implement",
    "fix", "change", "make", "use", "task", "feature", "component"
}


def normalize_keywords(text: str) -> List[str]:
    """
    Normalize text into keywords by:
    - Converting to lowercase
    - Extracting words (alphanumeric + hyphens)
    - Removing stop words
    - Filtering out short words (<3 chars)

    Args:
        text: Input text to normalize

    Returns:
        List of normalized keywords
    """
    # Extract words (lowercase, keep hyphens in compound words)
    words = re.findall(r'\b[a-z0-9]+(?:-[a-z0-9]+)*\b', text.lower())

    # Filter out stop words and short words
    keywords = [
        word for word in words
        if word not in STOP_WORDS and len(word) >= 3
    ]

    return keywords


def extract_task_keywords(task_description: str, max_keywords: int = 10) -> Set[str]:
    """
    Extract the most relevant keywords from a task description.

    Uses frequency analysis to identify the most important keywords,
    ignoring common stop words.

    Args:
        task_description: Task description text
        max_keywords: Maximum number of keywords to return

    Returns:
        Set of top keywords (up to max_keywords)
    """
    keywords = normalize_keywords(task_description)

    # Count frequency
    keyword_counts = Counter(keywords)

    # Get top N most common keywords
    top_keywords = {word for word, _ in keyword_counts.most_common(max_keywords)}

    return top_keywords


def keyword_overlap_score(text: str, keywords: Set[str]) -> int:
    """
    Calculate how many of the target keywords appear in the text.

    Args:
        text: Text to search
        keywords: Target keywords to look for

    Returns:
        Number of keywords found in text (0-N)
    """
    text_lower = text.lower()
    return sum(1 for keyword in keywords if keyword in text_lower)


def contains_any_keyword(text: str, keywords: Set[str]) -> bool:
    """
    Check if text contains any of the target keywords.

    Args:
        text: Text to search
        keywords: Target keywords to look for

    Returns:
        True if any keyword is found, False otherwise
    """
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in keywords)
