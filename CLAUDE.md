# CLAUDE.md

## Project Overview

**Claude Slack Bridge (Docker PTY Mode)** - Self-contained Docker solution running both the bridge AND Claude Code in a single container.

**Core Flow:**
```
Slack message → Bridge → PTY stdin → Claude Code
Claude Code → Stop hook → localhost POST → Bridge → Slack
```

**Key Features:**
- Single container deployment
- PTY-based input (no tmux)
- Hooks POST to localhost
- Volume-mounted workspaces
- Auto-restart on crash

---

## Quick Reference

| Task | Command |
|------|---------|
| Start | `docker compose up -d` |
| Stop | `docker compose down` |
| Rebuild | `docker compose up -d --build` |
| Logs | `docker logs claude-slack-docker -f` |
| Health | `curl http://localhost:9876/health` |
| Status | `curl http://localhost:9876/status` |
| Restart Claude | `curl -X POST http://localhost:9876/restart` |

---

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
│    ├── repo1/                          │
│    ├── repo2/                          │
│    └── ...                             │
└────────────────────────────────────────┘
          │ WebSocket (Socket Mode)
          ▼
    Slack #channel
```

---

## Project Structure

```
claude-slack-docker/
├── bridge/                 # Python package
│   ├── main.py            # FastAPI app (PTY mode)
│   ├── pty_controller.py  # PTY management (replaces tmux.py)
│   ├── slack_client.py    # Slack Socket Mode
│   ├── session_manager.py # Session tracking
│   ├── queue.py           # Message queue
│   ├── formatter.py       # Slack formatting
│   ├── config.py          # Configuration
│   ├── models.py          # Pydantic models
│   └── transcript.py      # Transcript parsing
├── hooks/
│   └── slack_hook.py      # Simplified hook (localhost POST)
├── scripts/
│   ├── entrypoint.sh      # Container entrypoint
│   └── setup-hooks.sh     # Hook installer
├── config.yaml            # Main config
├── docker-compose.yml     # Docker services + volumes
├── Dockerfile             # Container image
└── slack-manifest.json    # Slack app manifest
```

---

## Key Differences from tmux Mode

| Component | tmux Mode | Docker PTY Mode |
|-----------|-----------|-----------------|
| `tmux.py` | tmux subprocess calls | N/A (removed) |
| `pty_controller.py` | N/A | PTY fork/exec |
| Hooks | POST to host bridge | POST to localhost |
| File access | Full host | Mounted volumes |
| Claude lifecycle | External (user starts) | Managed by bridge |

---

## Configuration

### .env (Required)

```bash
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_APP_TOKEN=xapp-your-token
ANTHROPIC_API_KEY=sk-ant-your-key
CLAUDE_SLACK_BRIDGE_API_KEY=optional-security-key
```

### config.yaml

```yaml
slack:
  allowed_user_ids: []  # Empty = allow all

formatting:
  mode: "full"
  max_length: 3900
  long_output: "file"
  strip_ansi: true

sessions:
  channel_id: "C0XXXXXXXX"  # Required
```

### docker-compose.yml (Volume Mounts)

```yaml
volumes:
  # Mount your repos here
  - ~/GitHub/project1:/workspace/project1
  - ~/GitHub/project2:/workspace/project2
```

---

## Development

### Key Files to Modify

| Task | File |
|------|------|
| Change PTY behavior | `bridge/pty_controller.py` |
| Modify startup | `scripts/entrypoint.sh` |
| Change hook behavior | `hooks/slack_hook.py` |
| Add API endpoint | `bridge/main.py` |
| Update formatting | `bridge/formatter.py` |

### Testing Changes

```bash
# Rebuild and restart
docker compose up -d --build

# Watch logs
docker logs claude-slack-docker -f

# Check status
curl http://localhost:9876/status
```

---

## How It Works

### Startup Sequence

1. Container starts → `entrypoint.sh`
2. Hooks installed to `~/.claude/hooks/`
3. Bridge starts (uvicorn)
4. Bridge spawns Claude Code via PTY
5. Slack Socket Mode connects
6. Ready for messages

### Message Flow

**Slack → Claude:**
1. User sends message in Slack
2. Bridge receives via Socket Mode
3. Message queued
4. Sent to Claude via PTY stdin

**Claude → Slack:**
1. Claude finishes responding
2. Stop hook fires
3. Hook reads transcript, extracts text
4. POST to `http://localhost:9876/hook`
5. Bridge formats and posts to Slack

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Claude not running | `curl -X POST localhost:9876/restart` |
| No files visible | Check volume mounts in docker-compose.yml |
| Hook errors | Check container logs |
| Slack not connecting | Verify tokens in .env |
| API key errors | Check ANTHROPIC_API_KEY in .env |
