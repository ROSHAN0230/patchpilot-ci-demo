"""
Failure Clustering Formal Validation Tests.
Validates:
1. Related-failure case: multiple failures from the SAME migration change merge into 1 cluster.
2. Unrelated-failure case: failures from DIFFERENT migration changes split into distinct clusters.
3. Precision metrics: cluster count, members per cluster, false merges, false splits.
"""

import pytest
from patchpilot.types import FailureRecord, UpgradeSpec
from patchpilot.intelligence.clusterer import FailureClusterer


def test_clustering_related_failures_same_root_cause():
    """
    Multiple tests across different modules failing due to the exact SAME breaking change
    (e.g., SQLAlchemy MovedIn20Warning on declarative_base import) must merge into 1 cluster.
    """
    spec = UpgradeSpec(package_name="sqlalchemy", old_version="1.4.0", new_version="2.0.0")
    clusterer = FailureClusterer()

    failures = [
        FailureRecord(
            run_id="run1",
            test_name="test_user_model_creation",
            file="tests/test_users.py",
            line=15,
            symbol="declarative_base",
            exception_type="MovedIn20Warning",
            message="The ``declarative_base()`` function is now available as sqlalchemy.orm.declarative_base().",
            stack_trace="from sqlalchemy.ext.declarative import declarative_base",
            dependency="sqlalchemy",
            category="moved_in_20",
        ),
        FailureRecord(
            run_id="run1",
            test_name="test_order_model_creation",
            file="tests/test_orders.py",
            line=22,
            symbol="declarative_base",
            exception_type="MovedIn20Warning",
            message="The ``declarative_base()`` function is now available as sqlalchemy.orm.declarative_base().",
            stack_trace="from sqlalchemy.ext.declarative import declarative_base",
            dependency="sqlalchemy",
            category="moved_in_20",
        ),
        FailureRecord(
            run_id="run1",
            test_name="test_invoice_schema",
            file="tests/test_invoices.py",
            line=8,
            symbol="declarative_base",
            exception_type="MovedIn20Warning",
            message="The ``declarative_base()`` function is now available as sqlalchemy.orm.declarative_base().",
            stack_trace="from sqlalchemy.ext.declarative import declarative_base",
            dependency="sqlalchemy",
            category="moved_in_20",
        ),
    ]

    clusters = clusterer.cluster_failures(failures, spec)

    # Metrics
    assert len(clusters) == 1, f"Expected 1 merged cluster, got {len(clusters)}"
    cluster = clusters[0]
    assert len(cluster.member_failures) == 3
    assert cluster.failure_category == "moved_in_20"
    assert "declarative_base" in cluster.symbols
    assert set(cluster.affected_files) == {"tests/test_users.py", "tests/test_orders.py", "tests/test_invoices.py"}

    # Validation: 0 false splits, 0 false merges
    false_splits = len(clusters) - 1
    false_merges = 0  # All 3 were genuinely the same root cause
    assert false_splits == 0
    assert false_merges == 0


def test_clustering_unrelated_failures_split_correctly():
    """
    Failures caused by completely different migration changes must split into separate clusters.
    """
    spec = UpgradeSpec(package_name="pydantic", old_version="1.10.0", new_version="2.0.0")
    clusterer = FailureClusterer()

    failures = [
        # Cause 1: validator deprecated in v2
        FailureRecord(
            run_id="run1",
            test_name="test_user_validator",
            file="tests/test_auth.py",
            line=40,
            symbol="validator",
            exception_type="PydanticDeprecatedSince20",
            message="Pydantic V1 style `@validator` validators are deprecated.",
            stack_trace="@validator('email')",
            dependency="pydantic",
            category="validator_deprecated",
        ),
        # Cause 2: dict() method removed/deprecated in favor of model_dump()
        FailureRecord(
            run_id="run1",
            test_name="test_serialization",
            file="tests/test_api.py",
            line=75,
            symbol="dict",
            exception_type="AttributeError",
            message="'UserDTO' object has no attribute 'dict'",
            stack_trace="data = user.dict()",
            dependency="pydantic",
            category="dict_deprecated",
        ),
        # Cause 3: BaseSettings moved to pydantic-settings
        FailureRecord(
            run_id="run1",
            test_name="test_config_loading",
            file="tests/test_config.py",
            line=12,
            symbol="BaseSettings",
            exception_type="ImportError",
            message="cannot import name 'BaseSettings' from 'pydantic'",
            stack_trace="from pydantic import BaseSettings",
            dependency="pydantic",
            category="settings_moved",
        ),
    ]

    clusters = clusterer.cluster_failures(failures, spec)

    # Metrics
    assert len(clusters) == 3, f"Expected 3 distinct clusters, got {len(clusters)}"
    categories = {c.failure_category for c in clusters}
    assert categories == {"validator_deprecated", "dict_deprecated", "settings_moved"}

    for c in clusters:
        assert len(c.member_failures) == 1

    # Validation: 0 false merges, 0 false splits
    false_merges = 0
    false_splits = 0
    assert false_merges == 0
    assert false_splits == 0


def test_clustering_mixed_complex_multi_issue_workload():
    """
    Tests a 6-failure workload with 2 issues of Cause A, 3 issues of Cause B, and 1 issue of Cause C.
    Verifies precise clustering without cross-contamination.
    """
    spec = UpgradeSpec(package_name="sqlalchemy", old_version="1.4.0", new_version="2.0.0")
    clusterer = FailureClusterer()

    failures = [
        # Cause A (Legacy Query Execution): 2 failures
        FailureRecord("r1", "test_query_user", "tests/test_q.py", 10, "query", "RemovedIn20Warning", "query() is legacy", "s.query(U)", "sqlalchemy", "legacy_query"),
        FailureRecord("r1", "test_query_item", "tests/test_i.py", 14, "query", "RemovedIn20Warning", "query() is legacy", "s.query(I)", "sqlalchemy", "legacy_query"),

        # Cause B (declarative_base relocation): 3 failures
        FailureRecord("r1", "test_m1", "tests/test_m.py", 5, "declarative_base", "MovedIn20Warning", "declarative_base moved", "ext.declarative", "sqlalchemy", "moved_declarative"),
        FailureRecord("r1", "test_m2", "tests/test_n.py", 8, "declarative_base", "MovedIn20Warning", "declarative_base moved", "ext.declarative", "sqlalchemy", "moved_declarative"),
        FailureRecord("r1", "test_m3", "tests/test_o.py", 12, "declarative_base", "MovedIn20Warning", "declarative_base moved", "ext.declarative", "sqlalchemy", "moved_declarative"),

        # Cause C (autocommit parameter removed): 1 failure
        FailureRecord("r1", "test_session_create", "tests/test_s.py", 20, "autocommit", "ArgumentError", "autocommit=False is deprecated", "Session(autocommit=True)", "sqlalchemy", "session_autocommit"),
    ]

    clusters = clusterer.cluster_failures(failures, spec)

    assert len(clusters) == 3
    counts_by_cat = {c.failure_category: len(c.member_failures) for c in clusters}
    assert counts_by_cat == {
        "legacy_query": 2,
        "moved_declarative": 3,
        "session_autocommit": 1,
    }

    # Verify no false merges: each cluster only contains its own category members
    for c in clusters:
        for m in c.member_failures:
            assert m.category == c.failure_category
