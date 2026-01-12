"""Slack client using Socket Mode for the Claude Slack Bridge."""

import logging
import re
from typing import Any, Callable, Dict, List, Optional

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

from .channel_registry import ChannelRegistry
from .config import SlackConfig
from .formatter import OutputFormatter

logger = logging.getLogger(__name__)


class SlackBridge:
    """Slack client using Socket Mode - no public URL needed."""

    def __init__(
        self,
        config: SlackConfig,
        formatter: OutputFormatter,
        channel_registry: ChannelRegistry,
    ):
        """Initialize the Slack bridge.

        Args:
            config: Slack configuration
            formatter: Output formatter for messages
            channel_registry: Registry of channel-to-repo mappings
        """
        self.config = config
        self.formatter = formatter
        self.channel_registry = channel_registry
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
            logger.info(
                f"Slack event received: channel={event.get('channel')}, "
                f"user={event.get('user')}, subtype={event.get('subtype')}"
            )

            # Ignore bot messages
            if event.get("bot_id") or event.get("subtype"):
                logger.debug("Ignoring bot/subtype message")
                return

            user = event.get("user")
            channel = event.get("channel")

            if not self._validate_incoming(user, channel):
                return

            text = event.get("text", "")
            if not text.strip():
                return

            logger.info(f"Received message from {user} in {channel}: {text[:50]}...")

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
        - Channel is in our registered channels

        Args:
            user: User ID from the event
            channel: Channel ID from the event

        Returns:
            True if the message should be processed, False otherwise.
        """
        if not self.is_allowed_user(user):
            logger.debug(f"Ignoring action from unauthorized user: {user}")
            return False

        if not self.channel_registry.is_registered_channel(channel):
            logger.debug(f"Ignoring action from unregistered channel: {channel}")
            return False

        return True

    def post_message(
        self,
        text: str,
        channel_id: Optional[str] = None,
        blocks: Optional[List[Dict[str, Any]]] = None,
        thread_ts: Optional[str] = None,
    ) -> Optional[str]:
        """Post a message to a Slack channel.

        Args:
            text: Message text
            channel_id: Channel to post to (uses current channel if not specified)
            blocks: Optional Slack blocks
            thread_ts: Optional thread timestamp for replies

        Returns the message timestamp (ts), or None if posting failed.
        """
        if not channel_id:
            channel_id = self.channel_registry.get_current_channel()

        if not channel_id:
            logger.error("No channel specified and no current channel set")
            return None

        try:
            response = self.app.client.chat_postMessage(
                channel=channel_id,
                text=text,
                blocks=blocks,
                thread_ts=thread_ts,
            )
            return response.get("ts")
        except SlackApiError as e:
            logger.error(f"Failed to post message to {channel_id}: {e}")
            return None

    def post_to_channel(
        self,
        channel_id: str,
        text: str,
        blocks: Optional[List[Dict[str, Any]]] = None,
        thread_ts: Optional[str] = None,
    ) -> Optional[str]:
        """Post a message to a specific channel.

        Returns the message timestamp (ts), or None if posting failed.
        """
        return self.post_message(
            text=text,
            channel_id=channel_id,
            blocks=blocks,
            thread_ts=thread_ts,
        )

    def post_formatted(
        self,
        content: str,
        channel_id: Optional[str] = None,
        event_type: str = "message",
        thread_ts: Optional[str] = None,
    ) -> Optional[str]:
        """Post formatted content to a Slack channel.

        Uses the formatter to create proper Slack blocks.
        """
        formatted = self.formatter.format(content, event_type)
        return self.post_message(
            text=formatted.text,
            channel_id=channel_id,
            blocks=formatted.blocks,
            thread_ts=thread_ts,
        )

    def post_formatted_to_channel(
        self,
        channel_id: str,
        content: str,
        event_type: str = "message",
        thread_ts: Optional[str] = None,
    ) -> Optional[str]:
        """Post formatted content to a specific channel."""
        return self.post_formatted(
            content=content,
            channel_id=channel_id,
            event_type=event_type,
            thread_ts=thread_ts,
        )

    def post_interactive(
        self,
        question: str,
        options: List[str],
        channel_id: Optional[str] = None,
        thread_ts: Optional[str] = None,
    ) -> Optional[str]:
        """Post an interactive question with buttons."""
        blocks = self.formatter.format_interactive_question(question, options)
        return self.post_message(
            text=question,
            channel_id=channel_id,
            blocks=blocks,
            thread_ts=thread_ts,
        )

    def upload_file(
        self,
        content: str,
        channel_id: Optional[str] = None,
        filename: str = "output.txt",
        title: str = "Full Output",
    ) -> bool:
        """Upload content as a file to Slack.

        Used for long output that exceeds message limits.
        """
        if not channel_id:
            channel_id = self.channel_registry.get_current_channel()

        if not channel_id:
            logger.error("No channel specified and no current channel set")
            return False

        try:
            self.app.client.files_upload_v2(
                channel=channel_id,
                content=content,
                filename=filename,
                title=title,
            )
            return True
        except SlackApiError as e:
            logger.error(f"Failed to upload file to {channel_id}: {e}")
            return False

    def join_channel(self, channel_id: str) -> bool:
        """Join a specific channel."""
        try:
            self.app.client.conversations_join(channel=channel_id)
            logger.info(f"Joined channel: {channel_id}")
            return True
        except SlackApiError as e:
            if "missing_scope" in str(e) or "channel_not_found" in str(e):
                logger.warning(
                    f"Cannot join channel {channel_id}: {e}. "
                    "Invite the bot manually with /invite @BotName"
                )
            else:
                logger.error(f"Failed to join channel {channel_id}: {e}")
            return False

    def create_channel(self, name: str) -> Optional[str]:
        """Create a new public channel.

        Returns the channel ID if successful, None otherwise.
        """
        # Sanitize channel name (lowercase, no spaces, max 80 chars)
        clean_name = name.lower().replace(" ", "-")[:80]
        try:
            response = self.app.client.conversations_create(name=clean_name)
            channel_id = response["channel"]["id"]
            logger.info(f"Created channel #{clean_name} ({channel_id})")
            return channel_id
        except SlackApiError as e:
            if "name_taken" in str(e):
                logger.info(f"Channel #{clean_name} already exists")
                # Try to find the existing channel
                return self.find_channel_by_name(clean_name)
            logger.error(f"Failed to create channel {clean_name}: {e}")
            return None

    def find_channel_by_name(self, name: str) -> Optional[str]:
        """Find a channel ID by name."""
        try:
            response = self.app.client.conversations_list(types="public_channel")
            for channel in response.get("channels", []):
                if channel["name"] == name:
                    return channel["id"]
        except SlackApiError as e:
            logger.error(f"Failed to list channels: {e}")
        return None

    def join_all_channels(self) -> Dict[str, bool]:
        """Join all registered channels.

        Returns a dict of channel_id -> success status.
        """
        results = {}
        for channel_id in self.channel_registry.get_channel_ids():
            results[channel_id] = self.join_channel(channel_id)
        return results
