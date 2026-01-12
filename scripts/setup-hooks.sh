#!/bin/bash
# Setup Claude Code hooks inside the container

set -e

HOOK_DIR="$HOME/.claude/hooks"
SETTINGS_FILE="$HOME/.claude/settings.json"

echo "Setting up Claude Code hooks..."

# Create hooks directory
mkdir -p "$HOOK_DIR"

# Copy hook script
cp /app/hooks/slack_hook.py "$HOOK_DIR/"
chmod +x "$HOOK_DIR/slack_hook.py"

# Create or update settings.json with hook configuration
if [ -f "$SETTINGS_FILE" ]; then
    # Backup existing settings
    cp "$SETTINGS_FILE" "$SETTINGS_FILE.bak"
fi

# Create settings with hooks (using new format with string matcher)
cat > "$SETTINGS_FILE" << 'EOF'
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $HOME/.claude/hooks/slack_hook.py"
          }
        ]
      }
    ]
  }
}
EOF

# Create user config to skip initial setup and trust workspace
USER_CONFIG="$HOME/.claude.json"
cat > "$USER_CONFIG" << 'EOF'
{
  "theme": "dark",
  "firstStartTime": "2026-01-01T00:00:00.000Z",
  "userID": "docker-bridge-user",
  "hasCompletedOnboarding": true,
  "hasAcceptedTerms": true,
  "sonnet45MigrationComplete": true,
  "opus45MigrationComplete": true,
  "thinkingMigrationComplete": true,
  "trustedDirectories": ["/workspace"],
  "bypassPermissionsModeAccepted": true,
  "primaryApiKeySource": "env",
  "hasAcceptedEnvApiKey": true
}
EOF
chmod 600 "$USER_CONFIG"
echo "User config: $USER_CONFIG"

# Create projects directory with workspace config
PROJECTS_DIR="$HOME/.claude/projects/-workspace"
mkdir -p "$PROJECTS_DIR"
cat > "$PROJECTS_DIR/settings.json" << 'EOF'
{
  "trusted": true
}
EOF
echo "Workspace trusted: $PROJECTS_DIR"

echo "Hooks installed successfully!"
echo "Hook script: $HOOK_DIR/slack_hook.py"
echo "Settings: $SETTINGS_FILE"
