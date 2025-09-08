from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from pydantic import ConfigDict


class ScrapeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    nl_request: str = Field(..., description="Natural language task description")
    output_schema: Dict[str, Any] = Field(
        ..., alias="schema", description="JSON schema describing expected data"
    )
    example: Optional[Dict[str, Any]] = Field(
        None, description="Optional example output"
    )
    login_params: Optional[Dict[str, Any]] = Field(
        None, description="Optional generic login params"
    )
    parameters: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional named parameters to guide extraction, e.g., facility name",
    )
    target_urls: Optional[List[str]] = Field(
        None, description="Optional list of target URLs to start from"
    )


class ScrapeResponse(BaseModel):
    job_id: str
    execution_log: List[str]
    data: Dict[str, Any]
