from typing import List
from pydantic import BaseModel, validator


class TagList(BaseModel):
    __root__: List[str]

    @validator("__root__", each_item=True)
    def validate_tag(cls, v):
        if not v.isalnum():
            raise ValueError(f"Tag must be alphanumeric: {v}")
        return v.lower()
