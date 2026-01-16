"""Channel registry for multi-channel/multi-repo support."""

import logging
import os
import threading
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Fallback global state file for backward compatibility
GLOBAL_CHANNEL_STATE_FILE = os.path.expanduser("~/.claude/hooks/.current_channel")


@dataclass
class ChannelContext:
    """Context information for a channel."""

    channel_id: str
    repo_path: str
    channel_name: str


class ChannelRegistry:
    """Registry mapping channels to repos and tracking current context."""

    def __init__(self) -> None:
        self._channels: Dict[str, ChannelContext] = {}
        self._current_channel: Optional[str] = None
        self._lock = threading.Lock()

    def register_channel(
        self, channel_id: str, repo_path: str, name: str = ""
    ) -> None:
        """Register a channel-to-repo mapping."""
        self._channels[channel_id] = ChannelContext(
            channel_id=channel_id,
            repo_path=repo_path,
            channel_name=name,
        )
        logger.info(f"Registered channel {channel_id} -> {repo_path}")

    def get_repo_for_channel(self, channel_id: str) -> Optional[str]:
        """Get the repo path for a channel."""
        ctx = self._channels.get(channel_id)
        return ctx.repo_path if ctx else None

    def get_channel_name(self, channel_id: str) -> str:
        """Get the friendly name for a channel."""
        ctx = self._channels.get(channel_id)
        return ctx.channel_name if ctx else ""

    def is_registered_channel(self, channel_id: str) -> bool:
        """Check if a channel is registered."""
        return channel_id in self._channels

    def set_current_channel(self, channel_id: str) -> None:
        """Set the current active channel for response routing."""
        with self._lock:
            self._current_channel = channel_id
            # Get repo path for this channel to write state to per-repo location
            repo_path = self.get_repo_for_channel(channel_id)
            self._write_channel_state(channel_id, repo_path)
            logger.debug(f"Set current channel to {channel_id} (repo: {repo_path})")

    def get_current_channel(self) -> Optional[str]:
        """Get the current active channel."""
        with self._lock:
            return self._current_channel

    def _write_channel_state(
        self, channel_id: str, repo_path: Optional[str] = None
    ) -> None:
        """Write current channel to state file for hook to read.

        Always uses global ~/.claude/hooks/.current_channel to avoid
        writing to bind-mounted repo directories (which would be visible
        on the host and could interfere with local Claude sessions).
        """
        state_file = GLOBAL_CHANNEL_STATE_FILE
        try:
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            with open(state_file, "w") as f:
                f.write(channel_id)
            logger.debug(f"Wrote channel state to {state_file}")
        except OSError as e:
            logger.error(f"Failed to write channel state to {state_file}: {e}")

    def get_all_channels(self) -> Dict[str, ChannelContext]:
        """Get all registered channels."""
        return self._channels.copy()

    def get_channel_ids(self) -> list[str]:
        """Get list of all registered channel IDs."""
        return list(self._channels.keys())
