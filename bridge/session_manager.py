"""Session management for Claude Slack Bridge (multi-channel mode)."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ChannelSession:
    """Session info for a single channel."""

    channel_id: str
    repo_path: str
    last_activity: datetime = field(default_factory=datetime.utcnow)
    message_count: int = 0


class SessionManager:
    """Manage sessions across multiple channels."""

    def __init__(self, channel_configs: Dict[str, str]):
        """Initialize with channel-to-repo mappings.

        Args:
            channel_configs: Dict of channel_id -> repo_path
        """
        self.sessions: Dict[str, ChannelSession] = {}
        self.channel_configs = channel_configs
        self.current_channel: Optional[str] = None

    def get_or_create_session(self, channel_id: str) -> Optional[ChannelSession]:
        """Get or create a session for a channel."""
        if channel_id not in self.channel_configs:
            logger.warning(f"Unknown channel: {channel_id}")
            return None

        if channel_id not in self.sessions:
            self.sessions[channel_id] = ChannelSession(
                channel_id=channel_id, repo_path=self.channel_configs[channel_id]
            )
            logger.info(
                f"Created session for channel {channel_id} -> {self.channel_configs[channel_id]}"
            )

        return self.sessions[channel_id]

    def update_activity(self, channel_id: str) -> None:
        """Update last activity for a channel."""
        if channel_id in self.sessions:
            self.sessions[channel_id].last_activity = datetime.utcnow()
            self.sessions[channel_id].message_count += 1

    def set_current_channel(self, channel_id: str) -> None:
        """Set the currently active channel."""
        self.current_channel = channel_id

    def get_current_channel(self) -> Optional[str]:
        """Get the currently active channel."""
        return self.current_channel

    def get_repo_for_channel(self, channel_id: str) -> Optional[str]:
        """Get the repo path for a channel."""
        return self.channel_configs.get(channel_id)

    def get_session(self, channel_id: str) -> Optional[ChannelSession]:
        """Get session for a specific channel."""
        return self.sessions.get(channel_id)

    def get_all_sessions(self) -> Dict[str, ChannelSession]:
        """Get all active sessions."""
        return self.sessions.copy()

    def clear_session(self, channel_id: str) -> Optional[ChannelSession]:
        """Clear session for a specific channel."""
        session = self.sessions.pop(channel_id, None)
        if session:
            logger.info(f"Cleared session for channel: {channel_id}")
        return session
