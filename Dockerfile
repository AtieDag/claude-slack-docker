# Claude Slack Bridge - Docker PTY Mode
# This container runs both the bridge AND Claude Code

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (required for Claude Code npm installation)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code globally via npm
RUN npm install -g @anthropic-ai/claude-code

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY bridge/ ./bridge/
COPY hooks/ ./hooks/
COPY scripts/ ./scripts/
COPY config.yaml .

# Make scripts executable
RUN chmod +x /app/scripts/*.sh /app/hooks/*.py

# Create a non-root user for running Claude Code
RUN useradd -m -s /bin/bash claude && \
    mkdir -p /workspace && \
    chown -R claude:claude /workspace /app

# Create Claude config directory for the claude user
RUN mkdir -p /home/claude/.claude/hooks && \
    chown -R claude:claude /home/claude/.claude

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV CLAUDE_WORKING_DIR=/workspace
ENV CLAUDE_SLACK_BRIDGE_URL=http://localhost:9876
ENV HOME=/home/claude
ENV TERM=xterm-256color

# Switch to non-root user
USER claude

# Expose the bridge port
EXPOSE 9876

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9876/health || exit 1

# Use entrypoint script
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
