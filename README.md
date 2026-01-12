# Claude Slack Bridge (Docker PTY Mode)

Bidirectional bridge between Claude Code and Slack, running entirely in Docker. Claude Code runs inside the container with PTY control.

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

## Features

- Self-contained single Docker container
- **Multi-channel support** - Map each Slack channel to a different repo
- Auto-restart on crash
- Isolated environment
- PTY-based communication with Claude Code

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

# Required: Claude Code authentication (choose one)
# Option 1: OAuth token from Claude Code SDK (recommended)
ANTHROPIC_API_KEY=sk-ant-oat01-your-oauth-token

# Option 2: Standard Anthropic API key
# ANTHROPIC_API_KEY=sk-ant-api03-your-api-key

# Optional: API key for hook security
CLAUDE_SLACK_BRIDGE_API_KEY=your-secret-key
```

**Getting an OAuth Token:**
```bash
# Run this command and copy the token starting with sk-ant-oat01-
claude setup-token
```
The OAuth token is valid for 1 year and works with Claude Code SDK.

Edit `config.yaml` to map channels to repos:
```yaml
slack:
  allowed_user_ids:
    - "U0XXXXXXXX"  # Your Slack user ID

sessions:
  channels:
    "C0XXXXXXXX":  # #project-a channel
      repo: /workspace/project-a
      name: "Project A"
    "C0YYYYYYYY":  # #project-b channel
      repo: /workspace/project-b
      name: "Project B"
  default_repo: /workspace
```

### 4. Mount Your Repos

Edit `docker-compose.yml` to mount the repos referenced in config.yaml:

```yaml
volumes:
  # Mount repos that match your channel config
  - ~/GitHub/project-a:/workspace/project-a
  - ~/GitHub/project-b:/workspace/project-b
```

### 5. Start

```bash
docker compose up -d
```

### 6. Use

Send a message in any configured Slack channel. Claude Code will:
1. Automatically switch to the repo mapped to that channel
2. Process your request
3. Respond in the same channel

Each channel is isolated to its own repo - no need to `cd` manually.

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
  channels:             # Map channels to repos
    "C0XXXXXXXX":
      repo: /workspace/my-project
      name: "My Project"
  default_repo: /workspace
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SLACK_BOT_TOKEN` | Yes | Bot token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Yes | App token (`xapp-...`) |
| `ANTHROPIC_API_KEY` | Yes | OAuth token (`sk-ant-oat01-...`) or API key (`sk-ant-api03-...`) |
| `CLAUDE_SLACK_BRIDGE_API_KEY` | No | Hook authentication |

**Note:** OAuth tokens (`sk-ant-oat01-...`) are recommended. Generate with `claude setup-token`.

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
| "Invalid API key" error | Use OAuth token (`claude setup-token`) or valid API key |
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
├── bridge/                    # Python package
│   ├── main.py               # FastAPI app (PTY mode)
│   ├── pty_controller.py     # PTY management
│   ├── slack_client.py       # Slack Socket Mode
│   ├── channel_registry.py   # Channel-to-repo mapping
│   ├── session_manager.py    # Per-channel sessions
│   ├── formatter.py          # Slack formatting
│   └── ...
├── hooks/
│   └── slack_hook.py         # Hook for localhost
├── scripts/
│   ├── entrypoint.sh         # Container entrypoint
│   └── setup-hooks.sh        # Hook installer
├── config.yaml
├── docker-compose.yml
├── Dockerfile
└── slack-manifest.json
```

## License

MIT
