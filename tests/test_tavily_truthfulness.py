"""
Tests for Tavily Truthfulness & Fail-Closed Behavior.
Verifies that Tavily failures/unavailability never masquerade as official documentation.
"""

from unittest.mock import MagicMock, patch
import pytest
from patchpilot.types import UpgradeSpec, FailureCluster
from patchpilot.engine.evidence import TavilyEvidenceEngine


def test_tavily_no_api_key_fails_closed():
    engine = TavilyEvidenceEngine(api_key="")
    spec = UpgradeSpec(package_name="pydantic", old_version="1.10.14", new_version="2.6.4")
    cluster = FailureCluster(
        cluster_id="c1",
        dependency="pydantic",
        failure_category="deprecated_validator",
        exception_classes=["PydanticUserError"],
        symbols=["validator"],
        affected_files=["models.py"],
        member_failures=[],
        representative_failure=None,
    )

    pack = engine.assemble_evidence_pack(spec, [cluster])
    assert pack.status == "TAVILY_UNAVAILABLE"
    assert len(pack.items) == 0
    assert pack.error_message == "No Tavily API key provided"


def test_tavily_exception_fails_closed_without_fake_docs():
    engine = TavilyEvidenceEngine(api_key="tvly-mock-key")
    spec = UpgradeSpec(package_name="pydantic", old_version="1.10.14", new_version="2.6.4")
    cluster = FailureCluster(
        cluster_id="c1",
        dependency="pydantic",
        failure_category="deprecated_validator",
        exception_classes=["PydanticUserError"],
        symbols=["validator"],
        affected_files=["models.py"],
        member_failures=[],
        representative_failure=None,
    )

    with patch("tavily.TavilyClient") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.search.side_effect = ConnectionError("Tavily service unreachable")
        mock_client_cls.return_value = mock_instance

        pack = engine.assemble_evidence_pack(spec, [cluster])
        assert pack.status == "TAVILY_UNAVAILABLE"
        assert len(pack.items) == 0
        assert "Tavily search failed" in (pack.error_message or "")
        # Verify no items claim official_docs authority
        for it in pack.items:
            assert it.source_authority != "official_docs"


def test_tavily_empty_results():
    engine = TavilyEvidenceEngine(api_key="tvly-mock-key")
    spec = UpgradeSpec(package_name="pydantic", old_version="1.10.14", new_version="2.6.4")
    cluster = FailureCluster(
        cluster_id="c1",
        dependency="pydantic",
        failure_category="deprecated_validator",
        exception_classes=["PydanticUserError"],
        symbols=["validator"],
        affected_files=["models.py"],
        member_failures=[],
        representative_failure=None,
    )

    with patch("tavily.TavilyClient") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.search.return_value = {"results": []}
        mock_client_cls.return_value = mock_instance

        pack = engine.assemble_evidence_pack(spec, [cluster])
        assert pack.status == "TAVILY_EMPTY"
        assert len(pack.items) == 0


def test_tavily_retrieved_results():
    engine = TavilyEvidenceEngine(api_key="tvly-mock-key")
    spec = UpgradeSpec(package_name="pydantic", old_version="1.10.14", new_version="2.6.4")
    cluster = FailureCluster(
        cluster_id="c1",
        dependency="pydantic",
        failure_category="deprecated_validator",
        exception_classes=["PydanticUserError"],
        symbols=["validator"],
        affected_files=["models.py"],
        member_failures=[],
        representative_failure=None,
    )

    with patch("tavily.TavilyClient") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.search.return_value = {
            "results": [
                {
                    "url": "https://docs.pydantic.dev/latest/migration/",
                    "title": "Pydantic Migration Guide",
                    "content": "@validator is replaced by @field_validator",
                }
            ]
        }
        mock_client_cls.return_value = mock_instance

        pack = engine.assemble_evidence_pack(spec, [cluster])
        assert pack.status == "TAVILY_RETRIEVED"
        assert len(pack.items) == 1
        assert pack.items[0].url == "https://docs.pydantic.dev/latest/migration/"
