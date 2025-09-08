from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScrapeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    nl_request: str = Field(..., description="Natural language task description")
    output_schema: dict[str, Any] = Field(
        ..., alias="schema", description="JSON schema describing expected data"
    )
    example: dict[str, Any] | None = Field(None, description="Optional example output")
    login_params: dict[str, Any] | None = Field(
        None, description="Optional generic login params"
    )
    parameters: dict[str, Any] | None = Field(
        None,
        description="Optional named parameters to guide extraction, e.g., facility name",
    )
    target_urls: list[str] | None = Field(
        None, description="Optional list of target URLs to start from"
    )


class ScrapeResponse(BaseModel):
    job_id: str
    execution_log: list[str]
    data: dict[str, Any]
    status: str = "completed"  # Default to completed for backward compatibility
