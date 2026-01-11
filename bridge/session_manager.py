"""Session management for Claude Slack Bridge (single session mode)."""

import logging
from datetime import datetime
from typing import Optional

from .models import SessionInfo

logger = logging.getLogger(__name__)


class SessionManager:
    """Manage the single active Claude session."""

    def __init__(self, channel_id: str):
        """Initialize the session manager.

        Args:
            channel_id: The single Slack channel ID for all messages
        """
        self.channel_id = channel_id
        self.session: Optional[SessionInfo] = None

    def register_session(
        self,
        session_id: str,
        tmux_session: str,
    ) -> SessionInfo:
        """Register or update the active session.

        Args:
            session_id: Claude Code session ID
            tmux_session: tmux session name

        Returns:
            The created/updated SessionInfo
        """
        self.session = SessionInfo(
            session_id=session_id,
            tmux_session=tmux_session,
            slack_channel_id=self.channel_id,
            slack_channel_name="",  # Not used in single channel mode
        )

        logger.info(
            f"Registered session: {session_id} -> tmux:{tmux_session} -> channel:{self.channel_id}"
        )

        return self.session

    def get_session(self) -> Optional[SessionInfo]:
        """Get the current active session."""
        return self.session

    def get_channel_id(self) -> str:
        """Get the configured channel ID."""
        return self.channel_id

    def update_activity(self) -> None:
        """Update the last activity timestamp for the session."""
        if self.session:
            self.session.last_activity = datetime.utcnow()

    def clear_session(self) -> Optional[SessionInfo]:
        """Clear the current session.

        Returns the cleared session info, or None if no session was active.
        """
        session = self.session
        self.session = None
        if session:
            logger.info(f"Cleared session: {session.session_id}")
        return session

    def find_or_create_session_for_hook(
        self, session_id: str, tmux_session: Optional[str] = None
    ) -> SessionInfo:
        """Find existing session or create a new one for a hook event.

        In single session mode, we always update to the incoming session.

        Returns:
            The session info (always returns a valid session)
        """
        # If we have a session with the same ID, just update activity
        if self.session and self.session.session_id == session_id:
            self.update_activity()
            return self.session

        # Register new session (replaces any existing)
        return self.register_session(
            session_id=session_id,
            tmux_session=tmux_session or "unknown",
        )
