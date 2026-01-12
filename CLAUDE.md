# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Claude Slack Bridge (Docker PTY Mode)** - A self-contained Docker solution that runs a FastAPI bridge and Claude Code in a single container, enabling bidirectional Slack communication.

**Core Flow (Multi-Channel):**
```
Slack #channel-A → Bridge sets channel context → cd /workspace/repo-a → PTY stdin → Claude Code
Claude Code → Stop hook reads channel → POST to /hook with target_channel → Bridge → Slack #channel-A
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
┌──────────────────────────────────────────────┐
│ Docker Container                             │
│                                              │
│  ┌─────────────┐    PTY    ┌─────────┐      │
│  │ Bridge      │◄─────────►│ Claude  │      │
│  │ (FastAPI)   │           │ Code    │      │
│  │ :9876       │           │         │      │
│  └──────┬──────┘           └────┬────┘      │
│         │                       │           │
│         │ Hook POST (localhost) │           │
│         └───────────────────────┘           │
│                                             │
│  Channel Registry:                          │
│    #channel-A → /workspace/repo-a           │
│    #channel-B → /workspace/repo-b           │
│                                             │
│  /workspace (mounted volumes)               │
└─────────────────────────────────────────────┘
          │ WebSocket (Socket Mode)
          ▼
    Slack #channel-A, #channel-B, ...
```

**Key Components:**

- `bridge/main.py` - FastAPI app with lifespan management, `/hook` and `/restart` endpoints
- `bridge/channel_registry.py` - Maps Slack channels to repo paths, tracks current channel
- `bridge/pty_controller.py` - PTY fork/exec to spawn and manage Claude Code process
- `bridge/slack_client.py` - Slack Socket Mode client with multi-channel support
- `bridge/session_manager.py` - Per-channel session tracking
- `hooks/slack_hook.py` - Stop hook that reads channel context and POSTs to localhost bridge
- `scripts/entrypoint.sh` - Container entrypoint: sets up hooks, verifies Claude, starts uvicorn

**Message Flow:**

1. **Slack → Claude:** User message in #channel-A → SlackBridge validates channel → Set current channel context → cd to repo-a → MessageQueue → PTYController.send_input()
2. **Claude → Slack:** Claude finishes → Stop hook reads channel from state file → POST to `/hook` with target_channel → SlackBridge.post_formatted_to_channel()

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
  channels:
    "C0XXXXXXXX":  # #project-a channel
      repo: /workspace/project-a
      name: "Project A"
    "C0YYYYYYYY":  # #project-b channel
      repo: /workspace/project-b
      name: "Project B"
  default_repo: /workspace

slack:
  allowed_user_ids: []  # Empty = allow all

formatting:
  mode: "full"  # full | compact | code-only
  max_length: 3900
  long_output: "file"  # truncate | split | file
```

### Workspace Volumes

Edit `docker-compose.yml` to mount repos that match your channel config:

```yaml
volumes:
  - ~/GitHub/project-a:/workspace/project-a
  - ~/GitHub/project-b:/workspace/project-b
```

## Key Modification Points

| Change | File |
|--------|------|
| Channel-to-repo mapping | `bridge/channel_registry.py` |
| PTY behavior / Claude lifecycle | `bridge/pty_controller.py` |
| API endpoints / orchestration | `bridge/main.py` |
| Hook logic / channel routing | `hooks/slack_hook.py` |
| Slack message formatting | `bridge/formatter.py` |
| Container startup | `scripts/entrypoint.sh` |

## How Stop Hooks Work

1. Claude Code finishes a response
2. Stop hook (`~/.claude/hooks/stop.py`) fires
3. Hook reads transcript file to extract last assistant message
4. Hook reads current channel from `~/.claude/hooks/.current_channel` (written by bridge)
5. Hook POSTs to `http://localhost:9876/hook` with `target_channel` and message
6. Bridge receives via `/hook` endpoint and posts to the correct Slack channel

The hook uses MD5-based deduplication (stored in `~/.claude/hooks/.slack_hook_state`) to avoid posting the same message twice.
