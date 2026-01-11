"""Configuration management for the Claude Slack Bridge."""

import os
from pathlib import Path
from typing import List, Literal, Optional

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


class SessionsConfig(BaseModel):
    """Session management configuration."""

    channel_id: str = ""  # Single channel ID for all messages
    auto_archive_after: int = 3600  # seconds, 0 to disable


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


def validate_slack_tokens(config: Config) -> list[str]:
    """Validate Slack token formats and return list of errors.

    Returns an empty list if all tokens are valid.
    """
    errors = []

    # Validate bot token format (should start with xoxb-)
    if config.slack.bot_token:
        if not config.slack.bot_token.startswith("xoxb-"):
            errors.append(
                f"SLACK_BOT_TOKEN has invalid format. Expected 'xoxb-...' but got "
                f"'{config.slack.bot_token[:10]}...'. Check your token configuration."
            )
    else:
        errors.append("SLACK_BOT_TOKEN is required but not set.")

    # Validate app token format (should start with xapp-)
    if config.slack.app_token:
        if not config.slack.app_token.startswith("xapp-"):
            errors.append(
                f"SLACK_APP_TOKEN has invalid format. Expected 'xapp-...' but got "
                f"'{config.slack.app_token[:10]}...'. Check your token configuration."
            )
    else:
        errors.append("SLACK_APP_TOKEN is required but not set.")

    return errors


# Global config instance (lazy loaded)
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
