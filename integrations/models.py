"""Pydantic models for platform integration data."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# Mirror database ENUMs as string literals
PlatformType = Literal["telegram", "slack", "discord", "whatsapp"]
PlatformStatus = Literal["active", "paused", "error", "disconnected"]


class IncomingMessage(BaseModel):
    """Normalized incoming message from any platform."""

    platform: PlatformType
    external_user_id: str = Field(..., description="Platform-specific user ID")
    external_channel_id: str = Field(..., description="Chat/channel/DM ID")
    text: str = Field(..., description="Message text content")
    username: Optional[str] = Field(None, description="User display name")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    thread_id: Optional[str] = Field(None, description="Thread/reply ID if applicable")
    raw_payload: dict = Field(default_factory=dict, description="Original platform payload")


class OutgoingMessage(BaseModel):
    """Normalized outgoing message to any platform."""

    platform: PlatformType
    channel_id: str = Field(..., description="Destination channel/chat ID")
    text: str = Field(..., description="Message text (markdown)")
    thread_id: Optional[str] = Field(None, description="Reply to thread if applicable")
    formatted_text: Optional[str] = Field(None, description="Platform-specific formatted text")


class PlatformConfig(BaseModel):
    """Platform connection configuration."""

    platform: PlatformType
    credentials: dict = Field(..., description="Encrypted credentials (bot_token, etc.)")
    webhook_url: Optional[str] = Field(None, description="Webhook URL for this connection")
    external_bot_id: Optional[str] = Field(None, description="Platform bot identifier")


class WebhookEvent(BaseModel):
    """Outbound webhook event payload."""

    event_id: str = Field(..., description="Unique event ID (evt_xxx)")
    event_type: str = Field(..., description="conversation.created, message.created, etc.")
    team_id: UUID
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: dict = Field(..., description="Event-specific data")
