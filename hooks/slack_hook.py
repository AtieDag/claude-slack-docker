#!/usr/bin/env python3
"""
Claude Code hook that sends events to the Slack bridge.

Docker PTY mode version - hooks POST to localhost within the container.

This script is called by Claude Code hooks (Stop, Notification, PostToolUse)
and forwards the event to the bridge server via HTTP.
"""

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

# Bridge URL - always localhost in Docker mode
BRIDGE_URL = os.environ.get("CLAUDE_SLACK_BRIDGE_URL", "http://localhost:9876")


# State files are always in global ~/.claude/hooks to avoid writing to
# bind-mounted repo directories (which would be visible on the host)
HOOKS_DIR = os.path.expanduser("~/.claude/hooks")
STATE_FILE = os.path.join(HOOKS_DIR, ".slack_hook_state")
CHANNEL_STATE_FILE = os.path.join(HOOKS_DIR, ".current_channel")


def get_state_file() -> str:
    """Get the state file path for deduplication."""
    return STATE_FILE


def get_channel_state_file() -> str:
    """Get the channel state file path."""
    return CHANNEL_STATE_FILE


def get_message_hash(message: str) -> str:
    """Get a hash of the message for deduplication."""
    return hashlib.md5(message.encode()).hexdigest()


def is_duplicate_message(message: str) -> bool:
    """Check if this message was already sent."""
    if not message:
        return True

    current_hash = get_message_hash(message)
    state_file = get_state_file()

    try:
        if os.path.exists(state_file):
            with open(state_file, "r") as f:
                last_hash = f.read().strip()
                if last_hash == current_hash:
                    return True
    except (IOError, OSError) as e:
        print(f"Warning: Failed to read dedup state file: {e}", file=sys.stderr)

    return False


def mark_message_sent(message: str) -> None:
    """Mark a message as sent to avoid duplicates."""
    if not message:
        return

    state_file = get_state_file()
    try:
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        with open(state_file, "w") as f:
            f.write(get_message_hash(message))
    except (IOError, OSError) as e:
        print(f"Warning: Failed to write dedup state file: {e}", file=sys.stderr)


def get_current_channel() -> str:
    """Read the current target channel from state file.

    The bridge writes this file when processing incoming messages,
    so we know which channel to route responses to.
    """
    channel_state_file = get_channel_state_file()
    try:
        if os.path.exists(channel_state_file):
            with open(channel_state_file, "r") as f:
                return f.read().strip()
    except (IOError, OSError) as e:
        print(f"Warning: Failed to read channel state: {e}", file=sys.stderr)
    return ""


def get_last_assistant_message(transcript_path: str) -> str:
    """Extract the last assistant text message from the transcript.

    Looks for the most recent assistant message that contains actual text
    (not just tool_use blocks).
    """
    if not transcript_path or not os.path.exists(transcript_path):
        return ""

    try:
        with open(transcript_path, "r") as f:
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
        print(f"Warning: Failed to read transcript file: {e}", file=sys.stderr)

    return ""


def main():
    """Main hook handler."""
    # Read hook input from stdin
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    # Only process Stop events (ignore PostToolUse, etc.)
    event_name = hook_input.get("hook_event_name", "")
    if event_name != "Stop":
        print(json.dumps({"continue": False}))
        sys.exit(0)

    # Extract the actual Claude response from transcript
    transcript_path = hook_input.get("transcript_path", "")
    message = ""
    if transcript_path:
        message = get_last_assistant_message(transcript_path)

    # Check for duplicate - don't send same message twice
    if not message or is_duplicate_message(message):
        print(json.dumps({"continue": False}))
        sys.exit(0)

    # Add session info, message, and target channel
    hook_input["pty_session"] = "pty"  # Fixed value for Docker PTY mode
    hook_input["stop_hook_message"] = message
    hook_input["target_channel"] = get_current_channel()  # Channel to route response to

    # POST to bridge (localhost in Docker)
    try:
        headers = {"Content-Type": "application/json"}
        # Add API key if configured
        api_key = os.environ.get("CLAUDE_SLACK_BRIDGE_API_KEY")
        if api_key:
            headers["X-API-Key"] = api_key

        req = urllib.request.Request(
            f"{BRIDGE_URL}/hook",
            data=json.dumps(hook_input).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        # Mark as sent only if POST succeeded
        mark_message_sent(message)
    except urllib.error.URLError as e:
        print(f"Warning: Failed to connect to bridge at {BRIDGE_URL}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Unexpected error sending hook: {e}", file=sys.stderr)

    # Output JSON to allow Claude to continue
    print(json.dumps({"continue": False}))
    sys.exit(0)


if __name__ == "__main__":
    main()
