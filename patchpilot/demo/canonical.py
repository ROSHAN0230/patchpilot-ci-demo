"""
PatchPilot Canonical Live Recovery Demonstration (Milestone 6).
Executes the genuine, end-to-end autonomous recovery pipeline using:
- Real local subprocess test runner (pytest) producing authentic failures
- Real AST impact analysis and failure clustering
- Real Tavily web search for upstream migration docs
- Real Nemotron-3 Super 120B LLM calls on Nebius Token Factory
- Controlled adversarial fault injection on Candidate 1 (simulating naive codemod trap)
- Real cryptographic snapshot rollback (SHA-256 state restoration)
- Real Attempt 2 synthesis with negative feedback loop
- Contract-verified green resolution and cryptographic audit ledger sealing
"""

import os
import sys
import shutil
import tempfile
import time
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load root .env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from patchpilot.types import (
    DependencyDelta,
    VerificationContract,
    UpgradeStatus,
)
from patchpilot.sandbox.local import LocalSubprocessDriver
from patchpilot.failures import FailureNormalizer
from patchpilot.engine.evidence import TavilyEvidenceEngine
from patchpilot.engine.repair import NemotronRepairEngine
from patchpilot.engine.patch import ScopeEnforcedPatchManager
from patchpilot.verifier import ContractVerificationEngine
from patchpilot.telemetry import JsonlEventLogger
from patchpilot.controller import BoundedRecoveryController
from patchpilot.observability.audit import AuditLedgerVerifier
from patchpilot.state import compute_file_sha256

console = Console()


class AdversarialDemoRepairEngine(NemotronRepairEngine):
    """
    Real Nemotron repair engine with a controlled post-generation fault injector.
    Candidate 1: Model generates a candidate, then the harness adversarially strips
    mode='before' to simulate a naive migration codemod trap.
    Candidate 2: Receives real pytest regression negative feedback and synthesizes
    the full, correct migration with mode='before'.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attempt_turn = 0
        self.live_model_calls = 0

    def generate_candidate(
        self,
        delta: DependencyDelta,
        target_file: str,
        current_code: str,
        failures: list,
        docs_context: str,
        negative_feedback: Optional[str] = None,
        iteration: int = 1,
    ):
        self.attempt_turn += 1
        self.live_model_calls += 1

        clean_code, meta = super().generate_candidate(
            delta, target_file, current_code, failures, docs_context, negative_feedback, iteration
        )

        if iteration == 1 and not negative_feedback:
            console.print("  [bold yellow][FAULT INJECTOR][/bold yellow] Simulating naive codemod trap: stripping [cyan]mode='before'[/cyan] on Candidate 1...")
            import re
            clean_code = re.sub(r",\s*mode=[\"']before[\"']", "", clean_code)
            clean_code = re.sub(r"mode=[\"']before[\"']\s*,?", "", clean_code)
            clean_code = re.sub(r"\(\s*,\s*", "(", clean_code)
            meta["hypothesis"] = "Faulty candidate (mode='before' stripped by adversarial injector)"

        return clean_code, meta


def run_canonical_demo(
    target_dir: str = "runs",
    run_id: str = "canonical_live_demo",
) -> Dict[str, Any]:
    """
    Executes the genuine live demo of PatchPilot's autonomous recovery engine.
    """
    console.print(Panel(
        Text(
            "PATCHPILOT // LIVE AUTONOMOUS RECOVERY ENGINE\n"
            "Real AST Analysis · Real Tavily Search · Real Nemotron LLM · Real Rollback",
            style="bold green",
            justify="center",
        ),
        border_style="green",
    ))

    # Stage 0: Set up workspace from the pristine adversarial fixture
    fixture_src = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "benchmarks", "fixtures", "adversarial")
    )
    temp_dir = tempfile.mkdtemp(prefix="pp_live_demo_")
    repo_path = os.path.abspath(temp_dir)

    for item in os.listdir(fixture_src):
        s = os.path.join(fixture_src, item)
        d = os.path.join(repo_path, item)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)

    try:
        model_file = os.path.join(repo_path, "service_model.py")
        initial_hash = compute_file_sha256(model_file)
        console.print(f"\n[bold white]Target Fixture Initialized:[/bold white] [dim]{repo_path}[/dim]")
        console.print(f"Pristine [bold]service_model.py[/bold] SHA-256: [cyan]{initial_hash}[/cyan]")

        delta = DependencyDelta(
            package_name="pydantic",
            old_version="1.10.14",
            new_version="2.6.4",
            manifest_path="pyproject.toml",
            is_major_bump=True,
        )
        contract = VerificationContract(
            required_tests=["test_service.py"],
            allowed_file_scope=["service_model.py"],
            retry_budget=3,
        )

        nebius_key = os.environ.get("NEBIUS_API_KEY", "")
        tavily_key = os.environ.get("TAVILY_API_KEY", "")

        if not nebius_key:
            console.print("[bold red]ERROR: NEBIUS_API_KEY is not set in environment.[/bold red]")
            return {"status": "error", "error": "NEBIUS_API_KEY missing"}

        os.makedirs(target_dir, exist_ok=True)
        telemetry_path = os.path.join(target_dir, f"{run_id}_telemetry.jsonl")
        logger = JsonlEventLogger(log_path=telemetry_path)

        repair_engine = AdversarialDemoRepairEngine(api_key=nebius_key)
        evidence_engine = TavilyEvidenceEngine(api_key=tavily_key)
        sandbox = LocalSubprocessDriver()
        verifier = ContractVerificationEngine()
        patch_mgr = ScopeEnforcedPatchManager()
        failure_analyzer = FailureNormalizer()

        controller = BoundedRecoveryController(
            evidence_engine=evidence_engine,
            repair_engine=repair_engine,
            patch_manager=patch_mgr,
            sandbox=sandbox,
            verifier=verifier,
            failure_analyzer=failure_analyzer,
            recorder=logger,
            artifacts_dir=target_dir,
        )

        console.print("\n[bold cyan]Starting Bounded Recovery Controller Execution...[/bold cyan]")
        t0 = time.time()
        metrics = controller.execute_recovery(
            repo_dir=repo_path,
            contract=contract,
            delta=delta,
            run_id=run_id,
        )
        total_time = time.time() - t0

        # Verify audit ledger
        out_dir = metrics.bundle_dir or os.path.join(target_dir, run_id)
        audit_res = AuditLedgerVerifier.verify_run_bundle(out_dir)

        status_str = (
            "[bold green]VERIFIED_GREEN (100% Passed)[/bold green]"
            if metrics.final_status == UpgradeStatus.VERIFIED_GREEN
            else f"[bold red]{metrics.final_status.value}[/bold red]"
        )

        console.print("\n" + "=" * 70)
        console.print(Panel(
            f"[bold green]LIVE CANONICAL RECOVERY COMPLETE[/bold green]\n\n"
            f"Final Status: {status_str}\n"
            f"Run Artifact Bundle: [cyan]{out_dir}[/cyan]\n"
            f"Model Invocations: [bold]{repair_engine.live_model_calls}[/bold] (nvidia/nemotron-3-super-120b-a12b)\n"
            f"Attempts Synthesized: [bold]{metrics.attempts}[/bold]\n"
            f"Cryptographic Rollbacks: [bold]{metrics.rollback_count}[/bold]\n"
            f"Tavily Search Invocations: [bold]{metrics.tavily_calls}[/bold]\n"
            f"Total Recovery Duration: [bold]{total_time:.2f}s[/bold]\n"
            f"Root Hash: [cyan]{metrics.audit_root_hash}[/cyan]\n"
            f"Cryptographic Audit Ledger: {'[bold green]VALID / UNTAMPERED[/bold green]' if audit_res.get('verified') else '[bold red]FAILED[/bold red]'}\n\n"
            f"[dim]Artifacts generated: audit_manifest.json, bundle.json, candidates.json, telemetry.jsonl,\n"
            f"audit_ledger.jsonl, provenance.json, final_diff.patch, impact_graph.json[/dim]",
            border_style="green",
        ))

        return {
            "status": metrics.final_status.value,
            "run_id": run_id,
            "bundle_dir": out_dir,
            "root_hash": metrics.audit_root_hash,
            "audit_verified": audit_res.get("verified", False),
            "rollbacks": metrics.rollback_count,
            "attempts": metrics.attempts,
            "live_model_calls": repair_engine.live_model_calls,
            "runtime_seconds": total_time,
        }

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    res = run_canonical_demo()
    if res.get("status") == "verified_green":
        sys.exit(0)
    else:
        sys.exit(1)
