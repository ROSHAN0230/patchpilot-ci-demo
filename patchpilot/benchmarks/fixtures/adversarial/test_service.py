import pytest
import os
import sys
from pydantic import ValidationError

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from service_model import EventPayload


def test_1_event_with_dict_metadata():
    event = EventPayload(
        event_id="EVT-001",
        metadata={"cluster": "nebius-h100", "status": "active"},
    )
    assert event.event_id == "EVT-001"
    assert event.metadata["cluster"] == "nebius-h100"


def test_2_event_with_json_string_metadata():
    """
    CRITICAL ADVERSARIAL TRAP:
    Passes a raw JSON string.
    In Pydantic V2, this strictly requires @field_validator('metadata', mode='before') and @classmethod.
    Without mode='before', Pydantic V2 raises:
    ValidationError: Input should be a valid dictionary.
    """
    raw_json = '{"region": "us-central", "nodes": 16, "gpu": "h100"}'
    event = EventPayload(
        event_id="EVT-002",
        metadata=raw_json,
    )
    assert event.event_id == "EVT-002"
    assert isinstance(event.metadata, dict)
    assert event.metadata["nodes"] == 16
    assert event.metadata["gpu"] == "h100"


def test_3_invalid_json_fails_validation():
    with pytest.raises(ValidationError):
        EventPayload(
            event_id="EVT-003",
            metadata="not-a-json-string{",
        )
