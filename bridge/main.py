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
        logger.info(f"Sent message to Claude Code")
        if session_manager:
            session_manager.update_activity()
    else:
        logger.warning("Failed to send message to Claude Code")
    return success


def handle_slack_message(channel: str, user: str, text: str) -> None:
    """Handle incoming message from Slack."""
    if not session_manager:
        return

    if not PTYManager.is_running():
        logger.warning("Claude Code is not running for incoming Slack message")
        if slack:
            slack.post_message(
                ":warning: Claude Code is not running. Attempting to start..."
            )
            # Try to start Claude
            if PTYManager.start_claude():
                slack.post_message(":white_check_mark: Claude Code started!")
                time.sleep(2)  # Give it time to initialize
            else:
                slack.post_message(":x: Failed to start Claude Code")
                return

    # Queue the message for sending to Claude
    session = session_manager.get_session()
    if session and message_queue and main_event_loop:
        asyncio.run_coroutine_threadsafe(
            message_queue.enqueue(session.session_id, text),
            main_event_loop,
        )


def on_claude_output(text: str) -> None:
    """Handle output from Claude Code (for debugging)."""
    # Log output for debugging - log everything to see full prompts
    if text:
        # Strip ANSI codes for cleaner logging
        clean_text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
        # Log full output without truncation
        for line in clean_text.split('\n'):
            if line.strip():
                logger.info(f"Claude PTY: {line}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global slack, message_queue, main_event_loop, session_manager

    logger.info("Starting Claude Slack Bridge (Docker PTY mode)...")

    # Validate Slack tokens on startup
    token_errors = validate_slack_tokens(config)
    if token_errors:
        for error in token_errors:
            logger.error(error)
        raise ValueError("Invalid Slack token configuration. See errors above.")

    # Validate channel ID is configured
    if not config.sessions.channel_id:
        logger.error("No channel_id configured in sessions config!")
        raise ValueError("sessions.channel_id must be set in config.yaml")

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

    # Initialize session manager with the single channel
    session_manager = SessionManager(config.sessions.channel_id)

    # Initialize message queue
    message_queue = MessageQueue(send_callback=send_to_claude)

    # Initialize PTY manager
    working_dir = os.environ.get("CLAUDE_WORKING_DIR", "/workspace")
    PTYManager.initialize(working_dir=working_dir, on_output=on_claude_output)

    # Start Claude Code
    logger.info(f"Starting Claude Code in {working_dir}...")
    if PTYManager.start_claude():
        logger.info("Claude Code started successfully")
        # Create initial session
        session_manager.find_or_create_session_for_hook("docker-session", "pty")
    else:
        logger.warning("Failed to start Claude Code on startup")

    # Initialize Slack client with the channel ID
    slack = SlackBridge(config.slack, formatter, config.sessions.channel_id)

    # Set up callback
    slack.on_message_callback = handle_slack_message

    # Join the channel
    slack.join_channel()

    # Start Slack in background thread
    slack_thread = threading.Thread(target=slack.start, daemon=True)
    slack_thread.start()

    logger.info(f"Claude Slack Bridge started - using channel: {config.sessions.channel_id}")

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
        active_sessions=1 if PTYManager.is_running() else 0,
        slack_connected=slack is not None,
    )


def verify_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    """Verify API key if configured."""
    if config.bridge.api_key:
        if not x_api_key:
            raise HTTPException(
                status_code=401,
                detail="API key required. Set X-API-Key header."
            )
        if x_api_key != config.bridge.api_key:
            raise HTTPException(
                status_code=403,
                detail="Invalid API key."
            )


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

    if not session_manager or not slack:
        logger.warning("Hook received before bridge fully initialized")
        return JSONResponse({"status": "not_initialized"}, status_code=503)

    logger.info(
        f"Received hook event: {event.hook_event_name} for session {event.session_id}"
    )

    # Register/update the session
    session = session_manager.find_or_create_session_for_hook(
        event.session_id, "pty"  # Always "pty" in Docker mode
    )

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

        # Post to Slack if we have content
        if output and output.strip():
            logger.info(f"Posting to Slack: {output[:100]}...")
            slack.post_formatted(output, event_type="stop")
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
            status_code=500
        )


@app.get("/status")
async def get_status() -> JSONResponse:
    """Get detailed status."""
    session_data = None
    session = session_manager.get_session() if session_manager else None
    if session:
        session_data = {
            "session_id": session.session_id,
            "channel_id": session.slack_channel_id,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "last_activity": session.last_activity.isoformat() if session.last_activity else None,
        }
    return JSONResponse({
        "claude_running": PTYManager.is_running(),
        "slack_connected": slack is not None,
        "session": session_data,
        "working_dir": os.environ.get("CLAUDE_WORKING_DIR", "/workspace"),
    })


@app.post("/test")
async def send_test_message(
    x_api_key: Optional[str] = Header(None),
) -> JSONResponse:
    """Send a test message to Slack."""
    verify_api_key(x_api_key)

    if not slack:
        return JSONResponse(
            {"status": "error", "message": "Slack not connected"},
            status_code=503
        )

    try:
        slack.post_message(":white_check_mark: Test message from Claude Slack Bridge!")
        return JSONResponse({"status": "ok", "message": "Test message sent"})
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500
        )
