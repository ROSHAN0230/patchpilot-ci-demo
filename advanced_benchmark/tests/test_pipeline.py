import pytest
import os
import sys
from pydantic import ValidationError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from models.base import AuditBaseModel
from models.user import UserAccount
from services.processor import UserAccountProcessor

def test_1_base_config_assignment_and_forbid():
    """Verifies assignment validation and strict forbidding of extra fields."""
    class SampleModel(AuditBaseModel):
        name: str
        val: int

    m = SampleModel(name="test", val=10)
    assert m.name == "test"
    assert m.val == 10

    # Extra fields must be forbidden
    with pytest.raises(ValidationError):
        SampleModel(name="test", val=10, unknown_field="hacked")

def test_2_pre_validator_string_parsing_and_email():
    """Verifies that string-to-list coercion succeeds via pre-validation (mode='before')."""
    # Passing tags as a raw comma-delimited string
    user = UserAccount(
        user_id=101,
        email="  DevOps@Nebius.Cloud  ",
        tags="cloud, GPU, kubernetes",
    )
    assert user.email == "devops@nebius.cloud"
    assert user.tags == ["cloud", "gpu", "kubernetes"]

    # Invalid email must raise ValueError
    with pytest.raises(ValidationError):
        UserAccount(user_id=102, email="not-an-email", tags=["test"])

def test_3_processor_pipeline_and_export():
    """Verifies service parse_obj, copy update, and dict export."""
    raw = {
        "user_id": 202,
        "email": "agent@patchpilot.ai",
        "tags": "agentic, autonomous",
    }
    account = UserAccountProcessor.process_raw_registration(raw)
    assert account.user_id == 202
    assert "agentic" in account.tags

    updated = UserAccountProcessor.add_audit_tags(account, "verified")
    assert "verified" in updated.tags
    assert "verified" not in account.tags  # immutability check

    exported = UserAccountProcessor.export_for_storage(updated)
    assert isinstance(exported, dict)
    assert exported["user_id"] == 202
    assert "verified" in exported["tags"]
