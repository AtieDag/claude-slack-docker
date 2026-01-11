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

# Create settings with hooks
cat > "$SETTINGS_FILE" << 'EOF'
{
  "hooks": {
    "Stop": [
      {
        "type": "command",
        "command": "python3 $HOME/.claude/hooks/slack_hook.py"
      }
    ]
  }
}
EOF

echo "Hooks installed successfully!"
echo "Hook script: $HOOK_DIR/slack_hook.py"
echo "Settings: $SETTINGS_FILE"
