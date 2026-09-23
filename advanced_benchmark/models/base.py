"""
Base models with Pydantic v2 configuration.
Updated to use ConfigDict as required by Pydantic V2.
"""
from pydantic import BaseModel, ConfigDict


class AuditBaseModel(BaseModel):
    model_config = ConfigDict(
        validate_assignment=True,
        extra="forbid",
    )
