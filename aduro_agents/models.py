"""
Data models for the Aduro Health Assistant.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserIntent(str, Enum):
    """Possible user intents."""

    GREETING = "greeting"
    PROFILE_QUERY = "profile_query"
    PROFILE_UPDATE = "profile_update"
    CGM_QUERY = "cgm_query"
    CGM_UPDATE = "cgm_update"
    MEAL_QUERY = "meal_query"
    MEAL_PLAN = "meal_plan"
    UNKNOWN = "unknown"


class ProfileStatus(str, Enum):
    """Status of user profile completion."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


class UserProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str | None = None
    last_name: str | None = None
    city: str | None = None
    email: str | None = None
    date_of_birth: str | None = None  # Assuming YYYY-MM-DD string format
    dietary_preference: str | None = None
    medical_conditions: str | None = None
    physical_limitations: str | None = None


class AduroConversationContext(BaseModel):
    """Tracks the state of a conversation with the Aduro Health Assistant."""

    user_id: int | None = None
    current_intent: UserIntent | None = None
    profile_status: ProfileStatus = ProfileStatus.NOT_STARTED
    has_cgm_data: bool = False
    last_interaction: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def update_profile_status(self, profile_data: dict[str, Any]) -> None:
        """Update profile status based on profile data."""
        required_fields = [
            "first_name",
            "last_name",
            "email",
            "date_of_birth",
            "dietary_preference",
        ]

        if not all(profile_data.get(field) for field in required_fields):
            self.profile_status = ProfileStatus.INCOMPLETE
        else:
            self.profile_status = ProfileStatus.COMPLETE

        self.last_interaction = datetime.utcnow()

    def update_cgm_status(self, has_data: bool) -> None:
        """Update CGM data status."""
        self.has_cgm_data = has_data
        self.last_interaction = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AduroConversationContext":
        """Create from dictionary."""
        return cls(**data)
