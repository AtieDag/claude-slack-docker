# Claude Slack Bridge (Docker PTY Mode)

Bidirectional bridge between Claude Code and Slack, running entirely in Docker. Claude Code runs inside the container with PTY control - no tmux needed.

## Architecture

```
┌─────────────────────────────────────────┐
│ Docker Container                        │
│                                         │
│  ┌─────────────┐    PTY    ┌─────────┐ │
│  │ Bridge      │◄─────────►│ Claude  │ │
│  │ (FastAPI)   │           │ Code    │ │
│  └──────┬──────┘           └────┬────┘ │
│         │                       │      │
│         │ Hook POST (localhost) │      │
│         └───────────────────────┘      │
└─────────────────────────────────────────┘
          │ WebSocket
          ▼
       Slack
```

## Key Differences from tmux Mode

| Aspect | tmux Mode | Docker PTY Mode |
|--------|-----------|-----------------|
| Claude runs | On host | In container |
| Input method | tmux send-keys | PTY stdin |
| File access | Full host | Mounted volumes only |
| Dependencies | tmux, Python | Docker only |
| Setup | Multiple steps | Single container |

## Trade-offs

**Pros:**
- Self-contained (single Docker container)
- No tmux dependency
- Auto-restart on crash
- Isolated environment

**Cons:**
- Claude Code can only access mounted directories
- Need to explicitly mount each repo
- Container environment may differ from host

## Quick Start

### 1. Create Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App** → **From manifest**
3. Paste the contents of `slack-manifest.json`
4. Install to workspace

### 2. Get Tokens

**App Token:**
1. Go to **Basic Information** → **App-Level Tokens**
2. Generate token with `connections:write` scope
3. Copy the `xapp-...` token

**Bot Token:**
1. Go to **OAuth & Permissions**
2. Copy the `xoxb-...` token

### 3. Configure

Create `.env` file:
```bash
# Required: Slack tokens
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token

# Required: Anthropic API key for Claude Code
ANTHROPIC_API_KEY=sk-ant-your-key

# Optional: API key for hook security
CLAUDE_SLACK_BRIDGE_API_KEY=your-secret-key
```

Edit `config.yaml`:
```yaml
slack:
  allowed_user_ids:
    - "U0XXXXXXXX"  # Your Slack user ID

sessions:
  channel_id: "C0XXXXXXXX"  # Your Slack channel ID
```

### 4. Mount Your Repos

Edit `docker-compose.yml` to mount your repositories:

```yaml
volumes:
  # Mount specific repos
  - ~/GitHub/my-project:/workspace/my-project
  - ~/GitHub/another-repo:/workspace/another-repo

  # Or mount entire directory
  - ~/GitHub:/workspace
```

### 5. Start

```bash
docker compose up -d
```

### 6. Use

Send a message in your Slack channel. Claude Code will respond!

To work on a specific repo, tell Claude:
```
cd /workspace/my-project
```

## Commands

| Command | Description |
|---------|-------------|
| `docker compose up -d` | Start bridge |
| `docker compose down` | Stop bridge |
| `docker compose up -d --build` | Rebuild and start |
| `docker logs claude-slack-docker -f` | View logs |
| `curl localhost:9876/health` | Health check |
| `curl localhost:9876/status` | Detailed status |
| `curl -X POST localhost:9876/restart` | Restart Claude Code |

## Configuration

### config.yaml

```yaml
slack:
  allowed_user_ids: []  # Empty = allow all users

formatting:
  mode: "full"          # full | compact | code-only
  max_length: 3900
  long_output: "file"   # truncate | split | file
  strip_ansi: true

sessions:
  channel_id: ""        # Required: Slack channel ID
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SLACK_BOT_TOKEN` | Yes | Bot token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Yes | App token (`xapp-...`) |
| `ANTHROPIC_API_KEY` | Yes | For Claude Code |
| `CLAUDE_SLACK_BRIDGE_API_KEY` | No | Hook authentication |

## Volume Mounting Strategies

### Single Workspace (Convenient)
```yaml
volumes:
  - ~/GitHub:/workspace
```
Claude sees all repos but has broad access.

### Specific Repos (Isolated)
```yaml
volumes:
  - ~/GitHub/repo1:/workspace/repo1
  - ~/GitHub/repo2:/workspace/repo2
```
Claude only sees mounted repos.

### Project + Dependencies
```yaml
volumes:
  - ~/GitHub/main-project:/workspace/main-project
  - ~/GitHub/shared-lib:/workspace/shared-lib
  - ~/.ssh:/root/.ssh:ro  # For git operations
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Claude not responding | Check `docker logs claude-slack-docker` |
| No files in /workspace | Verify volume mounts in docker-compose.yml |
| Can't clone repos | Mount ~/.ssh for git access |
| "ANTHROPIC_API_KEY not set" | Add to .env file |
| Hook not firing | Check container logs for errors |

### Check Status

```bash
# Health check
curl http://localhost:9876/health

# Detailed status
curl http://localhost:9876/status

# Container logs
docker logs claude-slack-docker -f
```

## Project Structure

```
claude-slack-docker/
├── bridge/                 # Python package
│   ├── main.py            # FastAPI app (PTY mode)
│   ├── pty_controller.py  # PTY management
│   ├── slack_client.py    # Slack Socket Mode
│   ├── session_manager.py # Session tracking
│   ├── formatter.py       # Slack formatting
│   └── ...
├── hooks/
│   └── slack_hook.py      # Hook for localhost
├── scripts/
│   ├── entrypoint.sh      # Container entrypoint
│   └── setup-hooks.sh     # Hook installer
├── config.yaml
├── docker-compose.yml
├── Dockerfile
└── slack-manifest.json
```

## License

MIT
