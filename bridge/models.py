"""Pydantic models for the Claude Slack Bridge."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HookEvent(BaseModel):
    """Event received from Claude Code hooks."""

    session_id: str
    hook_event_name: str  # Stop, PostToolUse, Notification, etc.
    transcript_path: Optional[str] = None
    cwd: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_response: Optional[Dict[str, Any]] = None
    stop_hook_active: Optional[bool] = None
    stop_hook_message: Optional[str] = None  # Claude's response message
    pty_session: Optional[str] = None  # Added by hook script


class SlackMessage(BaseModel):
    """Incoming message from Slack."""

    channel: str
    user: str
    text: str
    ts: str  # Slack timestamp (message ID)
    thread_ts: Optional[str] = None


class SessionInfo(BaseModel):
    """Information about an active Claude session."""

    session_id: str
    pty_session: str  # PTY session identifier
    slack_channel_id: str
    slack_channel_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)


class FormattedOutput(BaseModel):
    """Formatted output ready for Slack."""

    text: str  # Fallback text for notifications
    blocks: List[Dict[str, Any]]  # Slack Block Kit blocks


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str
    active_sessions: int
    slack_connected: bool


class SessionListResponse(BaseModel):
    """Response for listing sessions."""

    sessions: List[SessionInfo]
