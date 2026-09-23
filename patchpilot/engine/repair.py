"""
NVIDIA Nemotron-3 Super 120B Code Remediation Engine on Nebius Token Factory.
"""

import re
import time
import requests
from typing import List, Dict, Any, Optional, Tuple
from patchpilot.types import DependencyDelta, FailureRecord
from patchpilot.contracts import RepairEngine


class NemotronRepairEngine(RepairEngine):
    """Generates candidate migration patches using nvidia/nemotron-3-super-120b-a12b."""

    def __init__(
        self,
        api_key: str,
        model_id: str = "nvidia/nemotron-3-super-120b-a12b",
        base_url: str = "https://api.tokenfactory.nebius.com/v1",
    ):
        self.api_key = api_key.strip()
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")

    def generate_candidate(
        self,
        delta: DependencyDelta,
        target_file: str,
        current_code: str,
        failures: List[FailureRecord],
        docs_context: str,
        negative_feedback: Optional[str] = None,
        iteration: int = 1,
    ) -> Tuple[str, Dict[str, Any]]:
        system_prompt = (
            f"You are PatchPilot, an autonomous Python migration engineer upgrading code for {delta.package_name} "
            f"from {delta.old_version} to {delta.new_version}.\n"
            "MIGRATION DIRECTIVES:\n"
            "- If migrating to Pydantic V2:\n"
            "  * Replace `class Config:` with `model_config = ConfigDict(...)` and replace `orm_mode = True` with `from_attributes = True`.\n"
            "  * Replace `.from_orm(obj)` with `model_validate(obj)`, replace `.dict(...)` with `.model_dump(...)`, and replace `.copy(update=...)` with `.model_copy(update=...)`.\n"
            "  * Replace `__root__ = ...` with `RootModel[...]` from `pydantic` and access elements via `.root`.\n"
            "  * Replace `Field(..., regex=...)` with `Field(..., pattern=...)`.\n"
            "  * Replace `@validator` with `@field_validator` and ALWAYS decorate with `@classmethod`. Note: `@field_validator` does NOT accept `each_item=True`; to validate collection elements, iterate over items in the validator method.\n"
            "STRICT RULES:\n"
            "1. Output ONLY the complete updated Python code inside a single ```python ... ``` block.\n"
            "2. Preserve all existing business logic, validation semantics, type hints, and function signatures.\n"
            "3. Do not include conversational remarks outside the code block."
        )

        feedback_block = ""
        if negative_feedback:
            feedback_block = f"""
PREVIOUS CANDIDATE FAILED WITH REGRESSION:
{negative_feedback}
Carefully inspect why the previous attempt broke tests and provide the corrected code.
"""

        error_summaries = "\n".join(
            [f"- [{f.category}] {f.exception_type}: {f.message} (Test: {f.test_name})" for f in failures[:5]]
        )

        user_prompt = f"""TARGET FILE: {target_file}

CURRENT CODE:
```python
{current_code}
```

FAILURES DETECTED:
{error_summaries}

OFFICIAL MIGRATION GUIDANCE:
{docs_context[:1500]}
{feedback_block}
Provide the complete updated Python code for {target_file} that satisfies all behavioral requirements."""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "max_tokens": 4000,
            "reasoning_effort": "low",
        }

        t0 = time.time()
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        elapsed_ms = (time.time() - t0) * 1000

        if resp.status_code != 200:
            raise RuntimeError(f"Nemotron inference failed: HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        usage = data.get("usage", {})
        inp_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        # Pricing: $0.0008 / 1k prompt, $0.002 / 1k completion
        cost = (inp_tok * 0.0008 / 1000.0) + (out_tok * 0.002 / 1000.0)

        msg = data["choices"][0]["message"]
        content = (msg.get("content") or "").strip()
        reasoning = (msg.get("reasoning") or "").strip()

        match = re.search(r"```python\s*\n(.*?)\n```", content, re.DOTALL)
        if not match and reasoning:
            match = re.search(r"```python\s*\n(.*?)\n```", reasoning, re.DOTALL)

        if not match:
            raise ValueError(f"Model failed to produce a valid Python code block. Response was: {content[:300]}")

        clean_code = match.group(1).strip() + "\n"
        meta = {
            "latency_ms": elapsed_ms,
            "input_tokens": inp_tok,
            "output_tokens": out_tok,
            "cost_usd": cost,
            "iteration": iteration,
        }
        return clean_code, meta
