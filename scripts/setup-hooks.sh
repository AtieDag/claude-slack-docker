#!/bin/bash
# Setup Claude Code hooks inside the container

set -e

HOOK_DIR="$HOME/.claude/hooks"
SETTINGS_FILE="$HOME/.claude/settings.json"
WORKSPACE_DIR="/workspace"

echo "Setting up Claude Code hooks..."

# Create global hooks directory
mkdir -p "$HOOK_DIR"

# Copy hook script to global location
cp /app/hooks/slack_hook.py "$HOOK_DIR/"
chmod +x "$HOOK_DIR/slack_hook.py"

# Initialize per-repo .claude/hooks directories
echo "Initializing per-repo .claude/hooks directories..."
if [ -d "$WORKSPACE_DIR" ]; then
    for repo_dir in "$WORKSPACE_DIR"/*/; do
        if [ -d "$repo_dir" ]; then
            repo_name=$(basename "$repo_dir")
            repo_hook_dir="${repo_dir}.claude/hooks"

            echo "  Setting up hooks in: $repo_dir"
            mkdir -p "$repo_hook_dir"

            # Copy hook script to per-repo location
            cp /app/hooks/slack_hook.py "$repo_hook_dir/"
            chmod +x "$repo_hook_dir/slack_hook.py"

            # Create per-repo trust settings
            repo_projects_dir="${repo_dir}.claude"
            cat > "$repo_projects_dir/settings.json" << 'EOF'
{
  "trusted": true
}
EOF
            echo "    Created: $repo_hook_dir"
        fi
    done
fi

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
