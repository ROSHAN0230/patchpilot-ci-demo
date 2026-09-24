import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("NEBIUS_API_KEY")
headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

system_prompt = (
    "You are a principal engineer migrating Python code from Pydantic V1 to V2.\n"
    "CRITICAL INSTRUCTIONS:\n"
    "1. Keep internal reasoning concise.\n"
    "2. Output the complete corrected python code for the target file inside a single ```python ... ``` block.\n"
    "3. Ensure the code block is valid, executable Python."
)

user_content = """FILE: core/config.py
CURRENT CODE:
from typing import List
from pydantic import BaseModel, validator

class TagList(BaseModel):
    __root__: List[str]

    @validator("__root__", each_item=True)
    def validate_tag(cls, v):
        if not v.isalnum():
            raise ValueError("Tags must be alphanumeric")
        return v.lower()

ERROR:
TypeError: To define root models, use `pydantic.RootModel` rather than a field called '__root__'

DOCS:
In Pydantic V2, replace __root__ with RootModel[List[str]] and use @field_validator('root') with mode='after' or validate items.
"""

payload = {
    "model": "nvidia/nemotron-3-super-120b-a12b",
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ],
    "max_tokens": 2000,
    "temperature": 0.0,
}

resp = requests.post("https://api.tokenfactory.nebius.com/v1/chat/completions", headers=headers, json=payload, timeout=40)
data = resp.json()
print("Usage:", data.get("usage"))
msg = data["choices"][0]["message"]
print("Reasoning snippet:", (msg.get("reasoning") or "")[:200])
print("Content:\n", msg.get("content"))
