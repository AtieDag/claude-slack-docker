# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Claude Slack Bridge (Docker PTY Mode)** - A self-contained Docker solution that runs a FastAPI bridge and Claude Code in a single container, enabling bidirectional Slack communication.

**Core Flow:**
```
Slack message → Bridge (FastAPI) → PTY stdin → Claude Code
Claude Code → Stop hook → localhost POST → Bridge → Slack
```

## Commands

| Task | Command |
|------|---------|
| Start | `docker compose up -d` |
| Stop | `docker compose down` |
| Rebuild | `docker compose up -d --build` |
| Logs | `docker logs claude-slack-docker -f` |
| Health check | `curl http://localhost:9876/health` |
| Status | `curl http://localhost:9876/status` |
| Restart Claude | `curl -X POST http://localhost:9876/restart` |

## Architecture

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

**Key Components:**

- `bridge/main.py` - FastAPI app with lifespan management, `/hook` and `/restart` endpoints
- `bridge/pty_controller.py` - PTY fork/exec to spawn and manage Claude Code process
- `bridge/slack_client.py` - Slack Socket Mode client with message callbacks
- `hooks/slack_hook.py` - Stop hook that POSTs Claude's response to localhost bridge
- `scripts/entrypoint.sh` - Container entrypoint: sets up hooks, verifies Claude, starts uvicorn

**Message Flow:**

1. **Slack → Claude:** User message → SlackBridge callback → MessageQueue → PTYController.send_input()
2. **Claude → Slack:** Claude finishes → Stop hook reads transcript → POST to `/hook` → SlackBridge.post_formatted()

## Configuration

### Required: `.env`

```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_SLACK_BRIDGE_API_KEY=optional-security-key
```

### Required: `config.yaml`

```yaml
sessions:
  channel_id: "C0XXXXXXXX"  # Slack channel ID (required)

slack:
  allowed_user_ids: []  # Empty = allow all

formatting:
  mode: "full"  # full | compact | code-only
  max_length: 3900
  long_output: "file"  # truncate | split | file
```

### Workspace Volumes

Edit `docker-compose.yml` to mount repositories:

```yaml
volumes:
  - ~/GitHub/my-project:/workspace/my-project
```

## Key Modification Points

| Change | File |
|--------|------|
| PTY behavior / Claude lifecycle | `bridge/pty_controller.py` |
| API endpoints | `bridge/main.py` |
| Hook logic / transcript parsing | `hooks/slack_hook.py` |
| Slack message formatting | `bridge/formatter.py` |
| Container startup | `scripts/entrypoint.sh` |

## How Stop Hooks Work

1. Claude Code finishes a response
2. Stop hook (`~/.claude/hooks/stop.py`) fires
3. Hook reads transcript file to extract last assistant message
4. Hook POSTs to `http://localhost:9876/hook` with the message
5. Bridge receives via `/hook` endpoint and posts to Slack

The hook uses MD5-based deduplication (stored in `~/.claude/hooks/.slack_hook_state`) to avoid posting the same message twice.
