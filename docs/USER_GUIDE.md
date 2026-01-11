# User Guide

This guide covers setting up and using the Claude Slack Bridge.

## Prerequisites

- Docker and Docker Compose
- A Slack workspace where you can create apps
- An Anthropic API key

## Setup

### 1. Create Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App** → **From manifest**
3. Select your workspace
4. Paste the contents of `slack-manifest.json`
5. Click **Create**
6. Click **Install to Workspace** and authorize

### 2. Get Tokens

**App Token (for Socket Mode):**
1. Go to **Basic Information** → **App-Level Tokens**
2. Click **Generate Token and Scopes**
3. Name it (e.g., "socket-mode")
4. Add scope: `connections:write`
5. Click **Generate**
6. Copy the `xapp-...` token

**Bot Token (for API calls):**
1. Go to **OAuth & Permissions**
2. Copy the **Bot User OAuth Token** (`xoxb-...`)

### 3. Get Channel ID

1. In Slack, right-click on your target channel
2. Click **View channel details**
3. At the bottom, copy the Channel ID (starts with `C`)

### 4. Configure Environment

Create `.env` file in the project root:

```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key

# Optional: secure the hook endpoint
CLAUDE_SLACK_BRIDGE_API_KEY=your-secret-key
```

### 5. Configure Application

Edit `config.yaml`:

```yaml
slack:
  allowed_user_ids: []  # Empty allows all users, or add specific user IDs

formatting:
  mode: "full"
  max_length: 3900
  long_output: "file"
  strip_ansi: true

sessions:
  channel_id: "C0XXXXXXXX"  # Your channel ID from step 3
```

### 6. Mount Workspaces

Edit `docker-compose.yml` to mount the repositories you want Claude to access:

```yaml
volumes:
  # Mount specific repos
  - ~/GitHub/my-project:/workspace/my-project
  - ~/GitHub/another-repo:/workspace/another-repo

  # Or mount an entire directory
  - ~/GitHub:/workspace
```

### 7. Start the Bridge

```bash
docker compose up -d
```

Check logs to verify startup:

```bash
docker logs claude-slack-docker -f
```

You should see:
```
Claude Slack Bridge - Docker PTY Mode
Setting up Claude Code hooks...
Claude Code started successfully
Claude Slack Bridge started - using channel: C0XXXXXXXX
```

## Usage

### Basic Interaction

Send a message in your configured Slack channel. Claude will respond in the same channel.

### Working with Repositories

Tell Claude which workspace to use:

```
cd /workspace/my-project
```

Then interact normally:

```
What does this codebase do?
```

```
Fix the bug in src/utils.py
```

### Commands

| Command | Description |
|---------|-------------|
| `docker compose up -d` | Start the bridge |
| `docker compose down` | Stop the bridge |
| `docker compose up -d --build` | Rebuild and restart |
| `docker logs claude-slack-docker -f` | View logs |
| `docker compose restart` | Restart container |

### Health Checks

```bash
# Quick health check
curl http://localhost:9876/health

# Detailed status
curl http://localhost:9876/status

# Restart Claude Code (without restarting container)
curl -X POST http://localhost:9876/restart
```

## Configuration Options

### Formatting Modes

In `config.yaml`, `formatting.mode` controls output style:

| Mode | Description |
|------|-------------|
| `full` | Complete output with formatting |
| `compact` | Condensed output |
| `code-only` | Only code blocks |

### Long Output Handling

`formatting.long_output` controls how long messages are handled:

| Option | Description |
|--------|-------------|
| `truncate` | Cut off at max_length |
| `split` | Split into multiple messages |
| `file` | Upload as a file attachment |

### User Filtering

To restrict access to specific users, add their Slack user IDs:

```yaml
slack:
  allowed_user_ids:
    - "U0XXXXXXXX"
    - "U0YYYYYYYY"
```

Find user IDs by clicking on a user's profile in Slack → **More** → **Copy member ID**.

## Troubleshooting

### Claude not responding

1. Check if Claude is running:
   ```bash
   curl http://localhost:9876/status
   ```

2. If not running, restart:
   ```bash
   curl -X POST http://localhost:9876/restart
   ```

3. Check logs for errors:
   ```bash
   docker logs claude-slack-docker -f
   ```

### "No files in /workspace"

Verify volume mounts in `docker-compose.yml`:
- Paths must be absolute or use `~` for home
- Check that source directories exist
- Restart after changing mounts: `docker compose up -d`

### Slack connection issues

1. Verify tokens in `.env` are correct
2. Ensure app is installed to workspace
3. Check that Socket Mode is enabled in app settings
4. Verify bot is invited to the channel

### API key errors

Ensure `ANTHROPIC_API_KEY` is set in `.env` and is valid.

### Hook not firing

Check container logs for hook-related errors:
```bash
docker logs claude-slack-docker 2>&1 | grep -i hook
```

## Updating

To update to a new version:

```bash
# Pull latest changes
git pull

# Rebuild and restart
docker compose up -d --build
```

## Stopping

```bash
# Stop container (preserves config volume)
docker compose down

# Stop and remove config volume
docker compose down -v
```
