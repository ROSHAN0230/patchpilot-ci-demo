import os
import sys
import pytest
from unittest.mock import MagicMock, patch

from patchpilot.demo.canonical import AdversarialDemoRepairEngine
from patchpilot.types import DependencyDelta, FailureRecord
from patchpilot.cli import build_parser


def test_adversarial_demo_repair_engine_candidate_fault():
    engine = AdversarialDemoRepairEngine(api_key="mock_key")
    delta = DependencyDelta("pydantic", "1.10.14", "2.6.4", "pyproject.toml", True)

    generated_code_v2 = (
        "from pydantic import BaseModel, field_validator\n"
        "class Event(BaseModel):\n"
        "    @field_validator('meta', mode='before')\n"
        "    @classmethod\n"
        "    def parse(cls, v): return v\n"
    )

    with patch.object(
        engine, "generate_candidate", wraps=engine.generate_candidate
    ), patch(
        "patchpilot.engine.repair.NemotronRepairEngine.generate_candidate",
        return_value=(generated_code_v2, {"hypothesis": "base v2"}),
    ):
        # Iteration 1: No negative feedback -> Adversarial strip of mode='before'
        cand1, meta1 = engine.generate_candidate(
            delta=delta,
            target_file="service_model.py",
            current_code="...",
            failures=[],
            docs_context="",
            negative_feedback=None,
            iteration=1,
        )
        assert "mode='before'" not in cand1
        assert "mode=\"before\"" not in cand1
        assert "@field_validator('meta')" in cand1
        assert "mode='before' stripped" in meta1.get("hypothesis", "")
        assert engine.live_model_calls == 1

        # Iteration 2: Negative feedback present -> Preserves correct mode='before'
        cand2, meta2 = engine.generate_candidate(
            delta=delta,
            target_file="service_model.py",
            current_code=cand1,
            failures=[],
            docs_context="",
            negative_feedback="ValidationError: Input should be a valid dictionary",
            iteration=2,
        )
        assert "mode='before'" in cand2
        assert engine.live_model_calls == 2


def test_cli_parser_options():
    parser = build_parser()
    args_demo = parser.parse_args(["demo", "--replay"])
    assert args_demo.command == "demo"
    assert args_demo.replay is True

    args_demo_live = parser.parse_args(["demo"])
    assert args_demo_live.replay is False

    args_recover = parser.parse_args(["recover", "--repo", "sample_repo", "--package", "click"])
    assert args_recover.command == "recover"
    assert args_recover.repo == "sample_repo"
    assert args_recover.package == "click"

    args_bench = parser.parse_args(["benchmark", "--run-all"])
    assert args_bench.command == "benchmark"
    assert args_bench.run_all is True
