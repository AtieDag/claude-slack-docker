"""Transcript parsing utilities for Claude Slack Bridge.

This module extracts assistant messages from Claude Code transcript files.

Note: The hook script (hooks/slack_hook.py) contains a copy of this logic
because hooks run as standalone scripts and cannot import from the bridge package.
Keep both implementations in sync when making changes.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_last_assistant_message(transcript_path: Optional[str]) -> Optional[str]:
    """Extract the last assistant text message from the transcript.

    The transcript is a JSON lines file with conversation messages.
    Only extracts text content, ignoring tool_use blocks.

    Args:
        transcript_path: Path to the transcript JSONL file.

    Returns:
        The text content of the last assistant message, or None if not found.
    """
    if not transcript_path:
        return None

    path = Path(transcript_path)
    if not path.exists():
        return None

    try:
        with open(path, "r") as f:
            lines = f.readlines()

        # Parse JSON lines in reverse to find last assistant message WITH TEXT
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                if msg.get("type") == "assistant":
                    message = msg.get("message", {})
                    content = message.get("content", [])

                    # Collect text blocks only (skip tool_use blocks)
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "").strip()
                            if text:
                                text_parts.append(text)
                        elif isinstance(block, str):
                            text_parts.append(block)

                    # Only return if we found actual text content
                    if text_parts:
                        return "\n".join(text_parts)
                    # Otherwise continue looking for a message with text
            except json.JSONDecodeError:
                continue
    except (IOError, OSError) as e:
        logger.warning(f"Failed to read transcript file {transcript_path}: {e}")

    return None
