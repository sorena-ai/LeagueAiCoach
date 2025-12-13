from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, field_validator
import json


class GameStats(BaseModel):
    """
    Model for validating game statistics JSON sent by the client.

    This is a flexible model that accepts any JSON structure since
    the client controls the format. The main validation is size checking
    to prevent excessively large payloads.
    """

    data: Dict[str, Any] = Field(
        ...,
        description="Game statistics data from the client (flexible structure)"
    )

    @field_validator('data')
    @classmethod
    def validate_size(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate that the game stats JSON is not too large.
        This prevents excessive token usage in the prompt.
        """
        from app.config import settings

        # Serialize to JSON to check byte size
        json_str = json.dumps(v, ensure_ascii=False)
        size_bytes = len(json_str.encode('utf-8'))

        if size_bytes > settings.max_game_stats_bytes:
            size_kb = size_bytes / 1024
            max_kb = settings.max_game_stats_kb
            raise ValueError(
                f"Game stats JSON too large: {size_kb:.1f}KB exceeds maximum {max_kb}KB"
            )

        return v

    def to_json_string(self) -> str:
        """Convert game stats to JSON string for inclusion in prompt."""
        return json.dumps(self.data, indent=2, ensure_ascii=False)
