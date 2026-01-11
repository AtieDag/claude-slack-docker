#!/bin/bash
# Entrypoint script for Claude Slack Bridge (Docker PTY mode)

set -e

echo "========================================"
echo "Claude Slack Bridge - Docker PTY Mode"
echo "========================================"

# Setup hooks
echo "Setting up Claude Code hooks..."
/app/scripts/setup-hooks.sh

# Verify Claude Code is installed
if ! command -v claude &> /dev/null; then
    echo "ERROR: Claude Code not found!"
    exit 1
fi

echo "Claude Code version: $(claude --version 2>/dev/null || echo 'unknown')"

# Check for Anthropic API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "WARNING: ANTHROPIC_API_KEY not set. Claude Code may not work."
fi

# Show workspace contents
echo ""
echo "Workspace contents (/workspace):"
ls -la /workspace 2>/dev/null || echo "  (empty or not mounted)"
echo ""

# Start the bridge
echo "Starting bridge on port 9876..."
exec python -m uvicorn bridge.main:app --host 0.0.0.0 --port 9876
