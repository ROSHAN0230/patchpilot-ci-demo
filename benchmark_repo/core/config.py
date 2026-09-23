from typing import List
from pydantic import RootModel, model_validator


class TagList(RootModel[List[str]]):
    @model_validator(mode="after")
    def _validate_and_normalize_tags(self) -> "TagList":
        # Validate each tag is alphanumeric
        for tag in self.root:
            if not tag.isalnum():
                raise ValueError("Tags must be alphanumeric")
        # Normalize to lowercase
        self.root = [tag.lower() for tag in self.root]
        return self
