from typing import Dict, Any
from pydantic import BaseModel, validator
import json


class EventPayload(BaseModel):
    event_id: str
    metadata: Dict[str, Any]

    @validator("metadata", pre=True)
    def parse_metadata_json(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception as e:
                raise ValueError(f"Invalid JSON string: {e}")
        return v
