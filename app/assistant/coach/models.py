"""
Assistant Models

Pydantic models for assistant responses.
"""

from pydantic import BaseModel, Field


class CoachResponse(BaseModel):
    """
    Structured coaching response for League of Legends in-game advice.

    This model represents the coach's analysis and recommendations based on
    the current game state, player question, and strategic context.
    """

    user_question: str = Field(
        description="A clear transcript of what the user asked in the input audio file in the last message."
    )
    advice: str = Field(
        description="Concise coaching advice that directly answers the player's question. One sentence for most questions, more if needed for complex topics. Speak naturally like a coach."
    )
