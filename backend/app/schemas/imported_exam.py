from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class ImportedQuestion(BaseModel):
    question_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)
    question_type: str = "subjective"
    options: dict = Field(default_factory=dict)
    marks: float = Field(..., gt=0)


class ImportedExamRequest(BaseModel):
    division: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    topic: Optional[str] = None

    paper_context: str = Field(..., min_length=1)

    questions: list[ImportedQuestion] = Field(..., min_length=1)

    duration_minutes: int = Field(default=30, ge=1, le=480)

    scheduled_start_at: Optional[datetime] = None
    scheduled_end_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_schedule(self):
        if (
            self.scheduled_start_at
            and self.scheduled_end_at
            and self.scheduled_end_at <= self.scheduled_start_at
        ):
            raise ValueError(
                "Scheduled end time must be after scheduled start time."
            )

        return self