"""Typed HTTP response contracts."""

from typing import Literal

from pydantic import BaseModel, Field


class ServiceResponse(BaseModel):
    service: str = Field(examples=["January"])
    status: Literal["ok"] = "ok"


class ErrorResponse(BaseModel):
    error_type: Literal["internal_error"]
    message: str
    request_id: str
