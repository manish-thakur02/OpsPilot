from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(min_length=1, max_length=2000)

    @field_validator('question')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Question cannot be blank')
        return value.strip()

class ChatResponse(BaseModel):
    answer: str
    route: Literal['POLICY', 'ANALYTICS', 'HYBRID', 'UNSUPPORTED']
    sources: list[dict[str, Any]]
    analytics: dict[str, Any] | None
    execution: dict[str, Any]
    errors: list[str]

class MetricResponse(BaseModel):
    metric: str
    population: str
    data: Any = None
    filters: dict[str, Any] = Field(default_factory=dict)
    notes: str = ''
    text: str | None = None
