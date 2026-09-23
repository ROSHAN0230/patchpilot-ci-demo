"""
Failure Normalization and Regression Comparison Engine.
Extracts structured FailureRecords from test runner outputs and tracks failure lifecycles.
"""

import re
from typing import List, Dict, Optional, Set
from patchpilot.types import FailureRecord, FailureComparison
from patchpilot.contracts import FailureAnalyzer


class FailureNormalizer(FailureAnalyzer):
    """Parses raw test output streams into typed FailureRecord structures."""

    def parse_test_output(
        self, run_id: str, test_output: str, dependency: str = "pydantic"
    ) -> List[FailureRecord]:
        records: List[FailureRecord] = []
        if not test_output:
            return records

        # Pattern 1: pytest summary failure lines: FAILED tests/test_foo.py::test_bar - Exception: msg or ERROR tests/...
        failed_lines = re.findall(
            r"(?:FAILED|ERROR)\s+([^\s:]+)(?:::([^\s\-]+))?(?:\s*-\s*([^\n]+))?", test_output
        )

        # Pattern 2: Exception blocks: E   ExceptionType: Message
        e_blocks = re.findall(r"^E\s+([A-Za-z0-9_.]*(?:Error|Exception|Warning|Failure)):\s*([^\n]+)", test_output, re.MULTILINE)
        default_exc = e_blocks[0][0] if e_blocks else "RuntimeFailure"
        default_msg = e_blocks[0][1] if e_blocks else "Test assertion failed"

        for match in failed_lines:
            file_path = match[0].replace("\\", "/").strip()
            test_name = match[1].strip() if match[1] else "collection_or_module_error"
            summary_msg = match[2].strip() if match[2] else default_msg

            # Extract specific line number if present in traceback for this file
            line_no: Optional[int] = None
            line_match = re.search(rf"{re.escape(file_path)}:(\d+):", test_output)
            if line_match:
                try:
                    line_no = int(line_match.group(1))
                except ValueError:
                    line_no = None

            # Determine category
            category = self._categorize_failure(summary_msg, default_exc, test_output)

            # Determine relevant symbol
            symbol = None
            if "validator" in summary_msg.lower():
                symbol = "validator"
            elif "dict" in summary_msg.lower() or "model_dump" in summary_msg.lower():
                symbol = "model_dump"
            elif "basesettings" in summary_msg.lower():
                symbol = "BaseSettings"

            record = FailureRecord(
                run_id=run_id,
                test_name=test_name,
                file=file_path,
                line=line_no,
                symbol=symbol,
                exception_type=default_exc,
                message=summary_msg,
                stack_trace=test_output[-1500:],
                dependency=dependency,
                category=category,
                related_files=[file_path],
            )
            records.append(record)

        # Fallback if no explicit FAILED summary lines found but exit code != 0
        if not records and ("FAILED" in test_output or "ERRORS" in test_output or "ERROR" in test_output or "Traceback" in test_output):
            records.append(
                FailureRecord(
                    run_id=run_id,
                    test_name="general_test_failure",
                    file="tests",
                    line=None,
                    symbol=None,
                    exception_type=default_exc,
                    message=default_msg,
                    stack_trace=test_output[-1500:],
                    dependency=dependency,
                    category=self._categorize_failure(default_msg, default_exc, test_output),
                    related_files=[],
                )
            )

        return records

    def _categorize_failure(self, msg: str, exc: str, full_output: str) -> str:
        # Check specific message and exception first
        specific = (msg + " " + exc).lower()
        if "basesettings" in specific or "pydantic-settings" in specific:
            return "missing_settings_package"
        if "field_validator" in specific or "validator" in specific:
            return "validator_deprecation"
        if "model_dump" in specific or "'dict'" in specific or ".dict()" in specific:
            return "model_dump_migration"
        if "regex" in specific and "pattern" in specific:
            return "regex_pattern_rename"
        if "validationerror" in specific or "mode='before'" in specific:
            return "validation_semantic_change"

        # Fallback to broader text if specific has no match
        combined = (specific + " " + full_output).lower()
        if "basesettings" in combined or "pydantic-settings" in combined:
            return "missing_settings_package"
        if "field_validator" in combined or "validator" in combined:
            return "validator_deprecation"
        if "model_dump" in combined or "'dict'" in combined:
            return "model_dump_migration"
        if "regex" in combined and "pattern" in combined:
            return "regex_pattern_rename"
        if "validationerror" in combined or "mode='before'" in combined:
            return "validation_semantic_change"
        return "general_migration_incompatibility"

    def compare_failures(
        self, baseline: List[FailureRecord], current: List[FailureRecord]
    ) -> FailureComparison:
        baseline_fingerprints: Dict[str, FailureRecord] = {f.fingerprint(): f for f in baseline}
        current_fingerprints: Dict[str, FailureRecord] = {f.fingerprint(): f for f in current}

        resolved: List[FailureRecord] = [
            f for fp, f in baseline_fingerprints.items() if fp not in current_fingerprints
        ]
        persistent: List[FailureRecord] = [
            f for fp, f in current_fingerprints.items() if fp in baseline_fingerprints
        ]
        regressions: List[FailureRecord] = [
            f for fp, f in current_fingerprints.items() if fp not in baseline_fingerprints
        ]

        return FailureComparison(
            resolved_failures=resolved,
            new_regressions=regressions,
            persistent_failures=persistent,
            has_regressions=len(regressions) > 0,
            is_fully_resolved=len(current) == 0,
        )
