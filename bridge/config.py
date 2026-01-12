"""Configuration management for the Claude Slack Bridge."""

import os
from pathlib import Path
from typing import Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class SlackConfig(BaseModel):
    """Slack-related configuration."""

    bot_token: str = ""
    app_token: str = ""
    allowed_user_ids: List[str] = Field(default_factory=list)


class BridgeConfig(BaseModel):
    """Bridge server configuration."""

    host: str = "0.0.0.0"
    port: int = 9876
    api_key: str = ""  # Optional API key for hook authentication


class FormattingConfig(BaseModel):
    """Output formatting configuration."""

    mode: Literal["full", "compact", "code-only"] = "full"
    max_length: int = 3900  # Slack limit is 4000
    long_output: Literal["truncate", "split", "file"] = "file"
    strip_ansi: bool = True
    preserve_code_blocks: bool = True


class ChannelConfig(BaseModel):
    """Configuration for a single channel."""

    repo: str  # Path to repo, e.g., "/workspace/my-project"
    name: str = ""  # Optional friendly name


class SessionsConfig(BaseModel):
    """Session management configuration."""

    # Multi-channel mode: map channel IDs to repo configs
    channels: Dict[str, ChannelConfig] = Field(default_factory=dict)
    default_repo: str = "/workspace"  # Fallback if no channel match
    auto_archive_after: int = 3600  # seconds, 0 to disable

    # Deprecated: single channel mode (for backward compatibility)
    channel_id: str = ""


class Config(BaseSettings):
    """Main configuration class."""

    slack: SlackConfig = Field(default_factory=SlackConfig)
    bridge: BridgeConfig = Field(default_factory=BridgeConfig)
    formatting: FormattingConfig = Field(default_factory=FormattingConfig)
    sessions: SessionsConfig = Field(default_factory=SessionsConfig)

    class Config:
        env_prefix = ""
        extra = "ignore"


def load_config(config_path: Optional[str] = None) -> Config:
    """Load configuration from YAML file and environment variables.

    Environment variables take precedence over YAML values.
    Handles backward compatibility for old single channel_id format.
    """
    # Default config path
    if config_path is None:
        config_path = os.environ.get(
            "CLAUDE_SLACK_CONFIG",
            str(Path(__file__).parent.parent / "config.yaml"),
        )

    # Load YAML config
    config_data = {}
    if Path(config_path).exists():
        with open(config_path) as f:
            config_data = yaml.safe_load(f) or {}

    # Handle backward compatibility for single channel_id
    sessions_data = config_data.get("sessions", {})
    if "channel_id" in sessions_data and "channels" not in sessions_data:
        # Old format - migrate to new format
        old_channel_id = sessions_data.get("channel_id", "")
        if old_channel_id:
            sessions_data["channels"] = {
                old_channel_id: {
                    "repo": "/workspace",
                    "name": "Default",
                }
            }
            config_data["sessions"] = sessions_data

    # Create config object
    config = Config(**config_data)

    # Override with environment variables
    if bot_token := os.environ.get("SLACK_BOT_TOKEN"):
        config.slack.bot_token = bot_token
    if app_token := os.environ.get("SLACK_APP_TOKEN"):
        config.slack.app_token = app_token
    if api_key := os.environ.get("CLAUDE_SLACK_BRIDGE_API_KEY"):
        config.bridge.api_key = api_key

    return config


def _validate_token(token: str, name: str, prefix: str) -> Optional[str]:
    """Validate a single token and return error message if invalid."""
    if not token:
        return f"{name} is required but not set."
    if not token.startswith(prefix):
        return (
            f"{name} has invalid format. Expected '{prefix}...' but got "
            f"'{token[:10]}...'. Check your token configuration."
        )
    return None


def validate_slack_tokens(config: Config) -> list[str]:
    """Validate Slack token formats and return list of errors."""
    errors = []

    if err := _validate_token(config.slack.bot_token, "SLACK_BOT_TOKEN", "xoxb-"):
        errors.append(err)
    if err := _validate_token(config.slack.app_token, "SLACK_APP_TOKEN", "xapp-"):
        errors.append(err)

    return errors


# Global config instance (lazy loaded)
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
