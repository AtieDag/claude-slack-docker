"""Slack client using Socket Mode for the Claude Slack Bridge."""

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Set

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

from .config import SlackConfig
from .formatter import OutputFormatter

logger = logging.getLogger(__name__)




class SlackBridge:
    """Slack client using Socket Mode - no public URL needed."""

    def __init__(
        self,
        config: SlackConfig,
        formatter: OutputFormatter,
        channel_id: str,
    ):
        """Initialize the Slack bridge.

        Args:
            config: Slack configuration
            formatter: Output formatter for messages
            channel_id: The single channel ID for all messages
        """
        self.config = config
        self.formatter = formatter
        self.channel_id = channel_id
        self.allowed_users = set(config.allowed_user_ids)

        # Initialize Slack app
        self.app = App(token=config.bot_token)
        self.handler = SocketModeHandler(self.app, config.app_token)

        # Callback for incoming messages (set by main.py)
        self.on_message_callback: Optional[Callable[[str, str, str], None]] = None

        # Register handlers
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register Slack event handlers."""

        @self.app.event("message")
        def handle_message(event: Dict[str, Any], say: Callable) -> None:
            """Handle incoming messages from Slack channels."""
            # Log all incoming events for debugging
            logger.info(f"Slack event received: channel={event.get('channel')}, user={event.get('user')}, subtype={event.get('subtype')}")

            # Ignore bot messages
            if event.get("bot_id") or event.get("subtype"):
                logger.debug(f"Ignoring bot/subtype message")
                return

            user = event.get("user")
            channel = event.get("channel")

            if not self._validate_incoming(user, channel):
                logger.info(f"Message filtered: expected channel {self.channel_id}, got {channel}")
                return

            text = event.get("text", "")
            if not text.strip():
                return

            logger.info(f"Received message from {user}: {text[:50]}...")

            if self.on_message_callback:
                self.on_message_callback(channel, user, text)

        @self.app.action(re.compile(r"choice_\d+"))
        def handle_button(ack: Callable, body: Dict[str, Any], say: Callable) -> None:
            """Handle button clicks for interactive prompts."""
            ack()

            user = body.get("user", {}).get("id")
            channel = body.get("channel", {}).get("id")

            if not self._validate_incoming(user, channel):
                return

            action = body.get("actions", [{}])[0]
            value = action.get("value", "")

            logger.info(f"Button clicked by {user}: {value}")

            if self.on_message_callback:
                self.on_message_callback(channel, user, value)

    def start(self) -> None:
        """Start the Socket Mode connection (blocking)."""
        logger.info("Starting Slack Socket Mode connection...")
        self.handler.start()

    def start_async(self) -> None:
        """Start the Socket Mode connection in a background thread."""
        logger.info("Starting Slack Socket Mode connection (async)...")
        self.handler.connect()

    def stop(self) -> None:
        """Stop the Socket Mode connection."""
        logger.info("Stopping Slack Socket Mode connection...")
        self.handler.close()

    def is_allowed_user(self, user_id: Optional[str]) -> bool:
        """Check if a user is allowed to interact with the bridge."""
        if not self.allowed_users:
            # If no allowed users configured, allow all
            return True
        return user_id in self.allowed_users

    def _validate_incoming(
        self,
        user: Optional[str],
        channel: Optional[str],
    ) -> bool:
        """Validate an incoming message/action from Slack.

        Checks:
        - User is in allowed list (or list is empty)
        - Channel matches configured channel

        Args:
            user: User ID from the event
            channel: Channel ID from the event

        Returns:
            True if the message should be processed, False otherwise.
        """
        if not self.is_allowed_user(user):
            logger.debug(f"Ignoring action from unauthorized user: {user}")
            return False

        if channel != self.channel_id:
            logger.debug(f"Ignoring action from other channel: {channel}")
            return False

        return True

    def post_message(
        self,
        text: str,
        blocks: Optional[List[Dict[str, Any]]] = None,
        thread_ts: Optional[str] = None,
    ) -> Optional[str]:
        """Post a message to the configured Slack channel.

        Returns the message timestamp (ts), or None if posting failed.
        """
        try:
            response = self.app.client.chat_postMessage(
                channel=self.channel_id,
                text=text,
                blocks=blocks,
                thread_ts=thread_ts,
            )
            return response.get("ts")
        except SlackApiError as e:
            logger.error(f"Failed to post message: {e}")
            return None

    def post_formatted(
        self,
        content: str,
        event_type: str = "message",
        thread_ts: Optional[str] = None,
    ) -> Optional[str]:
        """Post formatted content to the Slack channel.

        Uses the formatter to create proper Slack blocks.
        """
        formatted = self.formatter.format(content, event_type)
        return self.post_message(
            text=formatted.text,
            blocks=formatted.blocks,
            thread_ts=thread_ts,
        )

    def post_interactive(
        self,
        question: str,
        options: List[str],
        thread_ts: Optional[str] = None,
    ) -> Optional[str]:
        """Post an interactive question with buttons."""
        blocks = self.formatter.format_interactive_question(question, options)
        return self.post_message(
            text=question,
            blocks=blocks,
            thread_ts=thread_ts,
        )

    def upload_file(
        self,
        content: str,
        filename: str = "output.txt",
        title: str = "Full Output",
    ) -> bool:
        """Upload content as a file to Slack.

        Used for long output that exceeds message limits.
        """
        try:
            self.app.client.files_upload_v2(
                channel=self.channel_id,
                content=content,
                filename=filename,
                title=title,
            )
            return True
        except SlackApiError as e:
            logger.error(f"Failed to upload file: {e}")
            return False

    def join_channel(self) -> bool:
        """Join the configured channel (needed to post to it)."""
        try:
            self.app.client.conversations_join(channel=self.channel_id)
            return True
        except SlackApiError as e:
            logger.error(f"Failed to join channel {self.channel_id}: {e}")
            return False
