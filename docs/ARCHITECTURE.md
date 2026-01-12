# Architecture

This document describes the technical architecture of the Claude Slack Bridge (Docker PTY Mode).

## System Overview

```
┌─────────────────────────────────────────┐
│ Docker Container                        │
│                                         │
│  ┌─────────────┐    PTY    ┌─────────┐ │
│  │ Bridge      │◄─────────►│ Claude  │ │
│  │ (FastAPI)   │           │ Code    │ │
│  │ :9876       │           │         │ │
│  └──────┬──────┘           └────┬────┘ │
│         │                       │      │
│         │ Hook POST (localhost) │      │
│         └───────────────────────┘      │
│                                        │
│  /workspace (mounted volumes)          │
└────────────────────────────────────────┘
          │ WebSocket (Socket Mode)
          ▼
    Slack #channel
```

The bridge runs entirely within a single Docker container, managing both the FastAPI server and Claude Code process.

## Components

### Bridge (FastAPI)

**File:** `bridge/main.py`

The central coordinator that:
- Manages application lifecycle via FastAPI lifespan context
- Exposes HTTP endpoints (`/health`, `/status`, `/hook`, `/restart`)
- Coordinates between Slack client, message queue, and PTY controller
- Receives hook events from Claude Code and routes responses to Slack

### PTY Controller

**File:** `bridge/pty_controller.py`

Manages Claude Code as a child process using Unix pseudo-terminals (PTY):

- `PTYController` - Low-level PTY management
  - `start()` - Forks process, sets up PTY, executes `claude` command
  - `send_input()` - Writes to PTY master file descriptor
  - `_read_output()` - Background thread reading PTY output
  - `stop()` - Sends SIGINT, then SIGKILL if needed

- `PTYManager` - Singleton wrapper for global access
  - Class methods for `start_claude()`, `stop_claude()`, `send_input()`, `is_running()`

### Slack Client

**File:** `bridge/slack_client.py`

Handles Slack communication via Socket Mode (WebSocket):
- Connects using `SLACK_APP_TOKEN`
- Posts messages using `SLACK_BOT_TOKEN`
- Invokes callback on incoming messages
- Runs in a background thread

### Message Queue

**File:** `bridge/queue.py`

Queues incoming Slack messages for delivery to Claude:
- Async queue with configurable delay
- Calls `send_callback` to deliver messages to PTY

### Stop Hook

**File:** `hooks/slack_hook.py`

Python script installed as a Claude Code hook:
- Triggered when Claude finishes responding
- Reads transcript file to extract last assistant message
- POSTs to `http://localhost:9876/hook`
- Uses MD5 deduplication to prevent duplicate posts

### Formatter

**File:** `bridge/formatter.py`

Formats Claude's output for Slack:
- Strips ANSI escape codes
- Handles long output (truncate, split, or file upload)
- Configurable formatting modes

## Data Flow

### Slack → Claude

```
1. User sends message in Slack channel
2. SlackBridge receives via Socket Mode WebSocket
3. handle_slack_message() callback invoked
4. Message enqueued in MessageQueue
5. Queue calls send_callback → send_to_claude()
6. PTYManager.send_input() writes to PTY stdin
7. Claude Code receives and processes message
```

### Claude → Slack

```
1. Claude Code completes response
2. Stop hook fires (~/.claude/hooks/stop.py)
3. Hook reads transcript, extracts assistant text
4. Hook POSTs to http://localhost:9876/hook
5. receive_hook() endpoint processes HookEvent
6. SlackBridge.post_formatted() sends to Slack
```

## Container Startup

**File:** `scripts/entrypoint.sh`

1. Run `setup-hooks.sh` to install hooks to `~/.claude/hooks/`
2. Verify Claude Code is installed
3. Check for authentication (OAuth token or API key)
4. Start uvicorn with `bridge.main:app`

**File:** `bridge/main.py` (lifespan)

1. Validate Slack tokens
2. Validate `channel_id` configuration
3. Store event loop reference for thread callbacks
4. Initialize SessionManager, MessageQueue, PTYManager
5. Start Claude Code via PTY
6. Initialize SlackBridge and connect to Slack
7. Start Slack client in background thread

## Key Design Decisions

### PTY Process Management

The bridge directly forks and manages Claude Code via PTY:
- Single Claude session per container
- Bridge manages Claude lifecycle (auto-restart capability)
- Direct stdin/stdout communication

### Localhost Hook Communication

Hooks POST to `localhost:9876` within the container rather than an external host. This:
- Eliminates network exposure requirements
- Simplifies configuration (no host IP needed)
- Keeps all communication internal to the container

### Transcript-Based Response Extraction

The stop hook reads Claude's transcript file to extract responses rather than capturing PTY output directly. This ensures:
- Clean text without terminal control sequences
- Accurate message boundaries
- Access to structured message content

## Configuration

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `SLACK_BOT_TOKEN` | Slack API calls |
| `SLACK_APP_TOKEN` | Socket Mode connection |
| `ANTHROPIC_API_KEY` | Claude Code auth (OAuth token `sk-ant-oat01-...` or API key) |
| `CLAUDE_SLACK_BRIDGE_API_KEY` | Optional hook endpoint auth |
| `CLAUDE_WORKING_DIR` | Working directory (default: `/workspace`) |

### config.yaml

```yaml
slack:
  allowed_user_ids: []  # User filtering

formatting:
  mode: "full"          # Output format
  max_length: 3900      # Slack message limit
  long_output: "file"   # Long output handling

sessions:
  channel_id: ""        # Target Slack channel
```

## Security Considerations

- `CLAUDE_SLACK_BRIDGE_API_KEY` protects `/hook` endpoint from unauthorized posts
- `allowed_user_ids` restricts which Slack users can interact
- Volume mounts control file system access
- Container isolation limits blast radius
