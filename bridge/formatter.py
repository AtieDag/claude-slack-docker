"""Output formatting for Slack messages."""

import re
from typing import Any, Dict, List, Optional

from .config import FormattingConfig
from .models import FormattedOutput


class OutputFormatter:
    """Format Claude Code output for Slack."""

    # ANSI escape code pattern
    ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")

    # Code block pattern (markdown style)
    CODE_BLOCK_PATTERN = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)

    def __init__(self, config: FormattingConfig):
        """Initialize the formatter with configuration."""
        self.mode = config.mode
        self.max_length = config.max_length
        self.long_output = config.long_output
        self.strip_ansi = config.strip_ansi
        self.preserve_code_blocks = config.preserve_code_blocks

    def format(self, content: str, event_type: str = "message") -> FormattedOutput:
        """Format content for Slack.

        Args:
            content: Raw content from Claude Code
            event_type: Type of event (message, tool_use, stop, etc.)

        Returns:
            FormattedOutput with text fallback and Slack blocks
        """
        # Strip ANSI codes if configured
        if self.strip_ansi:
            content = self._strip_ansi(content)

        # Apply mode-specific formatting
        if self.mode == "code-only":
            content = self._extract_code_blocks(content)
        elif self.mode == "compact":
            content = self._make_compact(content)

        # Handle long output
        if len(content) > self.max_length:
            content, is_truncated = self._handle_long_output(content)
        else:
            is_truncated = False

        # Build Slack blocks
        blocks = self._build_blocks(content, event_type, is_truncated)

        return FormattedOutput(
            text=content[:500] if len(content) > 500 else content,  # Fallback text
            blocks=blocks,
        )

    def _strip_ansi(self, content: str) -> str:
        """Remove ANSI escape codes from content."""
        return self.ANSI_PATTERN.sub("", content)

    def _extract_code_blocks(self, content: str) -> str:
        """Extract only code blocks from content."""
        blocks = self.CODE_BLOCK_PATTERN.findall(content)
        if not blocks:
            # If no code blocks, look for inline code or return as-is
            return content

        result = []
        for lang, code in blocks:
            lang_str = f"```{lang}\n" if lang else "```\n"
            result.append(f"{lang_str}{code.strip()}\n```")

        return "\n\n".join(result)

    def _make_compact(self, content: str) -> str:
        """Make content more compact for Slack display."""
        # Remove excessive newlines
        content = re.sub(r"\n{3,}", "\n\n", content)

        # Remove leading/trailing whitespace from lines
        lines = [line.strip() for line in content.split("\n")]
        content = "\n".join(lines)

        return content.strip()

    def _handle_long_output(self, content: str) -> tuple[str, bool]:
        """Handle content that exceeds max length.

        Returns (processed_content, is_truncated)
        """
        if self.long_output == "truncate":
            # Truncate with ellipsis
            truncated = content[: self.max_length - 50]
            # Try to truncate at a newline
            last_newline = truncated.rfind("\n")
            if last_newline > self.max_length - 200:
                truncated = truncated[:last_newline]
            return truncated + "\n\n... (truncated)", True

        elif self.long_output == "split":
            # Return first chunk (caller should handle splitting)
            return content[: self.max_length - 50] + "\n\n... (continued)", True

        else:  # file
            # Return truncated preview, full content will be uploaded as file
            preview = content[: min(1000, self.max_length // 2)]
            return preview + "\n\n... (full output in file)", True

    def _build_blocks(
        self, content: str, event_type: str, is_truncated: bool
    ) -> List[Dict[str, Any]]:
        """Build Slack Block Kit blocks from content."""
        blocks: List[Dict[str, Any]] = []

        # Convert markdown to Slack mrkdwn format
        content = self._convert_to_slack_mrkdwn(content)

        # Main content section
        # Split into chunks if needed (Slack text block limit is 3000 chars)
        chunk_size = 2900
        content_chunks = [
            content[i : i + chunk_size] for i in range(0, len(content), chunk_size)
        ]

        for chunk in content_chunks[:5]:  # Max 5 chunks in blocks
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": chunk,
                    },
                }
            )

        # Add truncation notice if needed
        if is_truncated:
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "_Output truncated..._",
                        }
                    ],
                }
            )

        return blocks

    def _convert_to_slack_mrkdwn(self, content: str) -> str:
        """Convert markdown to Slack mrkdwn format."""
        # Headers: ## Header -> *Header*
        content = re.sub(r'^#{1,6}\s+(.+)$', r'*\1*', content, flags=re.MULTILINE)

        # Bold: **text** -> *text*
        content = re.sub(r'\*\*(.+?)\*\*', r'*\1*', content)

        # Italic: _text_ stays the same in Slack

        # Links: [text](url) -> <url|text>
        content = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<\2|\1>', content)

        # Clean up excessive newlines
        content = re.sub(r'\n{3,}', '\n\n', content)

        return content.strip()

    def format_interactive_question(
        self, question: str, options: List[str]
    ) -> List[Dict[str, Any]]:
        """Format an interactive question with buttons.

        Used for AskUserQuestion and Y/N prompts from Claude.
        """
        blocks: List[Dict[str, Any]] = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":question: *{question}*",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": opt[:75]},  # Button text limit
                        "value": opt,
                        "action_id": f"choice_{i}",
                    }
                    for i, opt in enumerate(options[:5])  # Max 5 buttons
                ],
            },
        ]

        return blocks

    def format_session_created(
        self, session_name: str, channel_id: str
    ) -> List[Dict[str, Any]]:
        """Format a session created notification."""
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":rocket: *Claude session started*\n\nSession: `{session_name}`\nChannel: <#{channel_id}>",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Send messages here to chat with Claude. Use `/claude-stop` to end the session.",
                    }
                ],
            },
        ]

    def format_error(self, error: str) -> List[Dict[str, Any]]:
        """Format an error message."""
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":x: *Error*\n\n```{error}```",
                },
            }
        ]
