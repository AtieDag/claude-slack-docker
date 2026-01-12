"""Main FastAPI application for Claude Slack Bridge (Docker PTY mode)."""

import asyncio
import logging
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from . import __version__
from .channel_registry import ChannelRegistry
from .config import get_config, validate_slack_tokens
from .formatter import OutputFormatter
from .models import HealthResponse, HookEvent
from .pty_controller import PTYManager
from .queue import MessageQueue
from .session_manager import SessionManager
from .slack_client import SlackBridge
from .transcript import get_last_assistant_message

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global components
config = get_config()
formatter = OutputFormatter(config.formatting)
channel_registry: Optional[ChannelRegistry] = None
session_manager: Optional[SessionManager] = None
slack: Optional[SlackBridge] = None
message_queue: Optional[MessageQueue] = None
main_event_loop: Optional[asyncio.AbstractEventLoop] = None


def send_to_claude(session_id: str, message: str) -> bool:
    """Send a message to Claude Code via PTY."""
    if not PTYManager.is_running():
        logger.warning("Claude Code is not running")
        return False

    success = PTYManager.send_input(message)
    if success:
        logger.info("Sent message to Claude Code")
        # Update activity for current channel
        if session_manager and channel_registry:
            current_channel = channel_registry.get_current_channel()
            if current_channel:
                session_manager.update_activity(current_channel)
    else:
        logger.warning("Failed to send message to Claude Code")
    return success


def handle_slack_message(channel: str, user: str, text: str) -> None:
    """Handle incoming message from Slack."""
    if not session_manager or not channel_registry:
        return

    if not PTYManager.is_running():
        logger.warning("Claude Code is not running for incoming Slack message")
        if slack:
            slack.post_message(
                ":warning: Claude Code is not running. Attempting to start...",
                channel_id=channel,
            )
            # Try to start Claude
            if PTYManager.start_claude():
                slack.post_message(
                    ":white_check_mark: Claude Code started!", channel_id=channel
                )
                time.sleep(2)  # Give it time to initialize
            else:
                slack.post_message(
                    ":x: Failed to start Claude Code", channel_id=channel
                )
                return

    # Set current channel context for response routing
    channel_registry.set_current_channel(channel)
    session_manager.set_current_channel(channel)

    # Get repo for this channel and switch directory if needed
    repo_path = channel_registry.get_repo_for_channel(channel)
    if repo_path:
        current_dir = PTYManager.get_current_directory()
        if current_dir != repo_path:
            logger.info(f"Switching directory from {current_dir} to {repo_path}")
            PTYManager.change_directory(repo_path)

    # Queue the message for sending to Claude
    session = session_manager.get_or_create_session(channel)
    if session and message_queue and main_event_loop:
        asyncio.run_coroutine_threadsafe(
            message_queue.enqueue(f"channel-{channel}", text),
            main_event_loop,
        )


def on_claude_output(text: str) -> None:
    """Handle output from Claude Code (for debugging)."""
    # Log output for debugging - log everything to see full prompts
    if text:
        # Strip ANSI codes for cleaner logging
        clean_text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
        # Log full output without truncation
        for line in clean_text.split("\n"):
            if line.strip():
                logger.info(f"Claude PTY: {line}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global slack, message_queue, main_event_loop, session_manager, channel_registry

    logger.info("Starting Claude Slack Bridge (Docker PTY mode)...")

    # Validate Slack tokens on startup
    token_errors = validate_slack_tokens(config)
    if token_errors:
        for error in token_errors:
            logger.error(error)
        raise ValueError("Invalid Slack token configuration. See errors above.")

    # Validate channels are configured
    if not config.sessions.channels:
        logger.error("No channels configured in sessions config!")
        raise ValueError(
            "sessions.channels must be set in config.yaml. "
            "Example:\n"
            "sessions:\n"
            "  channels:\n"
            '    "C0XXXXXXXX":\n'
            "      repo: /workspace/my-project"
        )

    # Log API key status
    if config.bridge.api_key:
        logger.info("API key authentication enabled for /hook endpoint")
    else:
        logger.warning(
            "No API key configured. /hook endpoint is unprotected. "
            "Set CLAUDE_SLACK_BRIDGE_API_KEY for security."
        )

    # Store the event loop for use in threaded callbacks
    main_event_loop = asyncio.get_event_loop()

    # Build channel registry and configs from config
    channel_registry = ChannelRegistry()
    channel_configs = {}

    for channel_id, channel_cfg in config.sessions.channels.items():
        channel_registry.register_channel(
            channel_id, channel_cfg.repo, channel_cfg.name
        )
        channel_configs[channel_id] = channel_cfg.repo

    logger.info(f"Registered {len(channel_configs)} channel(s):")
    for channel_id, repo in channel_configs.items():
        logger.info(f"  {channel_id} -> {repo}")

    # Initialize session manager with channel configs
    session_manager = SessionManager(channel_configs)

    # Initialize message queue
    message_queue = MessageQueue(send_callback=send_to_claude)

    # Initialize PTY manager with default working directory
    # (actual directory will be set per-message based on channel)
    default_working_dir = config.sessions.default_repo
    PTYManager.initialize(working_dir=default_working_dir, on_output=on_claude_output)
    PTYManager.set_current_directory(default_working_dir)

    # Start Claude Code
    logger.info(f"Starting Claude Code in {default_working_dir}...")
    if PTYManager.start_claude():
        logger.info("Claude Code started successfully")
    else:
        logger.warning("Failed to start Claude Code on startup")

    # Initialize Slack client with channel registry
    slack = SlackBridge(config.slack, formatter, channel_registry)

    # Set up callback
    slack.on_message_callback = handle_slack_message

    # Join all configured channels
    join_results = slack.join_all_channels()
    for channel_id, success in join_results.items():
        if success:
            logger.info(f"Joined channel: {channel_id}")
        else:
            logger.error(f"Failed to join channel: {channel_id}")

    # Start Slack in background thread
    slack_thread = threading.Thread(target=slack.start, daemon=True)
    slack_thread.start()

    channel_list = ", ".join(channel_configs.keys())
    logger.info(f"Claude Slack Bridge started - channels: {channel_list}")

    yield

    # Cleanup
    logger.info("Shutting down Claude Slack Bridge...")

    if message_queue:
        await message_queue.shutdown()

    # Stop Claude Code
    PTYManager.stop_claude()

    if slack:
        slack.stop()

    logger.info("Claude Slack Bridge shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Claude Slack Bridge (Docker)",
    description="Bidirectional bridge between Claude Code and Slack (Docker PTY mode)",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="ok" if PTYManager.is_running() else "claude_not_running",
        version=__version__,
        active_sessions=len(session_manager.sessions) if session_manager else 0,
        slack_connected=slack is not None,
    )


def verify_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    """Verify API key if configured."""
    if config.bridge.api_key:
        if not x_api_key:
            raise HTTPException(
                status_code=401, detail="API key required. Set X-API-Key header."
            )
        if x_api_key != config.bridge.api_key:
            raise HTTPException(status_code=403, detail="Invalid API key.")


@app.post("/hook")
async def receive_hook(
    event: HookEvent,
    x_api_key: Optional[str] = Header(None),
) -> JSONResponse:
    """Receive hook events from Claude Code.

    In Docker mode, hooks POST to localhost within the container.
    """
    # Verify API key if configured
    verify_api_key(x_api_key)

    if not session_manager or not slack or not channel_registry:
        logger.warning("Hook received before bridge fully initialized")
        return JSONResponse({"status": "not_initialized"}, status_code=503)

    logger.info(
        f"Received hook event: {event.hook_event_name} for session {event.session_id}"
    )

    # Determine target channel for response
    target_channel = event.target_channel
    if not target_channel:
        # Fallback to current channel from session manager
        target_channel = session_manager.get_current_channel()

    if not target_channel:
        logger.warning("No target channel for hook response")
        return JSONResponse({"status": "no_target_channel"}, status_code=400)

    logger.info(f"Target channel for response: {target_channel}")

    # Handle Stop event - Claude finished responding
    if event.hook_event_name == "Stop":
        # Try to get Claude's actual response (in order of preference)
        output = None

        # 1. Try stop_hook_message (direct from hook)
        if event.stop_hook_message:
            output = event.stop_hook_message
            logger.info(f"Got stop_hook_message: {output[:100]}...")

        # 2. Try reading from transcript file
        if not output and event.transcript_path:
            logger.info(f"Reading transcript from: {event.transcript_path}")
            output = get_last_assistant_message(event.transcript_path)
            if output:
                logger.info(f"Got transcript message: {output[:100]}...")
            else:
                logger.warning("No message found in transcript")

        # Post to the correct Slack channel
        if output and output.strip():
            logger.info(f"Posting to Slack channel {target_channel}: {output[:100]}...")
            slack.post_formatted_to_channel(target_channel, output, event_type="stop")
        else:
            logger.warning("No output to post to Slack")

    return JSONResponse({"status": "ok"})


@app.post("/restart")
async def restart_claude(
    x_api_key: Optional[str] = Header(None),
) -> JSONResponse:
    """Restart Claude Code."""
    verify_api_key(x_api_key)

    logger.info("Restarting Claude Code...")
    PTYManager.stop_claude()

    if PTYManager.start_claude():
        logger.info("Claude Code restarted successfully")
        return JSONResponse({"status": "ok", "message": "Claude Code restarted"})
    else:
        logger.error("Failed to restart Claude Code")
        return JSONResponse(
            {"status": "error", "message": "Failed to restart Claude Code"},
            status_code=500,
        )


@app.get("/status")
async def get_status() -> JSONResponse:
    """Get detailed status."""
    # Build channel info
    channels_info = {}
    if channel_registry:
        for channel_id, ctx in channel_registry.get_all_channels().items():
            session = session_manager.get_session(channel_id) if session_manager else None
            channels_info[channel_id] = {
                "name": ctx.channel_name,
                "repo": ctx.repo_path,
                "session": {
                    "message_count": session.message_count if session else 0,
                    "last_activity": (
                        session.last_activity.isoformat() if session else None
                    ),
                }
                if session
                else None,
            }

    return JSONResponse(
        {
            "claude_running": PTYManager.is_running(),
            "slack_connected": slack is not None,
            "current_channel": (
                channel_registry.get_current_channel() if channel_registry else None
            ),
            "current_directory": PTYManager.get_current_directory(),
            "channels": channels_info,
        }
    )


@app.post("/test")
async def send_test_message(
    x_api_key: Optional[str] = Header(None),
) -> JSONResponse:
    """Send a test message to all configured Slack channels."""
    verify_api_key(x_api_key)

    if not slack or not channel_registry:
        return JSONResponse(
            {"status": "error", "message": "Slack not connected"}, status_code=503
        )

    try:
        results = {}
        for channel_id in channel_registry.get_channel_ids():
            success = slack.post_message(
                ":white_check_mark: Test message from Claude Slack Bridge!",
                channel_id=channel_id,
            )
            results[channel_id] = "sent" if success else "failed"
        return JSONResponse({"status": "ok", "results": results})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
