"""
Event processing schema using Pydantic v2.
Pre‑validation deserializes JSON strings into dictionaries.
"""
from typing import Dict, Any
from pydantic import BaseModel, field_validator
import json


class EventPayload(BaseModel):
    event_id: str
    metadata: Dict[str, Any]

    @field_validator("metadata", mode="before")
    @classmethod
    def parse_metadata_json(cls, v, info):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception as e:
                raise ValueError(f"Invalid JSON string: {e}")
        return v
