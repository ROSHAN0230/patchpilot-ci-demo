# PatchPilot 🧑‍✈️
### Autonomous Breaking-Change Recovery & Dependency Upgrade Engineer
**NVIDIA × Nebius AI Hackathon 2026** | *Track: Coding & Agentic Engineering*

[![CI](https://img.shields.io/badge/GitHub_Actions-Run_%2335993907979-success?logo=github-actions)](https://github.com/ROSHAN0230/patchpilot-ci-demo/actions/runs/35993907979)
[![Verified PR](https://img.shields.io/badge/PR_%231-100%25_Verified_Green-10b981?logo=github)](https://github.com/ROSHAN0230/patchpilot-ci-demo/pull/1)
[![Model](https://img.shields.io/badge/Model-NVIDIA_Nemotron--3_Super_120B-76b900?logo=nvidia)](https://nebius.com)
[![Inference](https://img.shields.io/badge/Inference-Nebius_Token_Factory-00d4ff)](https://nebius.com)
[![Audit](https://img.shields.io/badge/Audit_Ledger-SHA--256_Chained_Merkle_Seal-059669)](file:///runs/canonical_live_demo/audit_manifest.json)
[![Tests](https://img.shields.io/badge/Tests-56%2F56_Passing_Green-brightgreen)](tests/)

---

## ⚡ Executive Summary

Major dependency upgrades are a significant source of friction in software maintenance. Automated dependency bumpers modify package version strings in `pyproject.toml` or `package.json`, leaving developers to diagnose breaking changes, failing tests, and API deprecations manually. Meanwhile, general-purpose LLM assistants typically operate on full-file prompts without dependency-aware topological ordering or rollback safety mechanisms.

**PatchPilot** provides an autonomous breaking-change recovery workflow for dependency migrations:
1. **Dependency-Aware Impact Topography**: Constructs an AST-grounded `ImpactGraph` and `FailureClusters` before modifying application code.
2. **Authoritative Upstream Evidence**: Dynamically queries the **Tavily AI Search API** for official migration guides and deprecation changelogs.
3. **Surgical Patch Synthesis**: Leverages **NVIDIA Nemotron-3 Super 120B** via the **Nebius Token Factory** using targeted context slices.
4. **Enforces Execution Safety**: Validates candidate patches in an isolated sandbox (`local_subprocess_isolated`) with **byte-level SHA-256 Atomic Snapshot Rollback** whenever verification fails.
5. **Cryptographically Sealed Audit Ledger**: Emits a chained SHA-256 event ledger and 12-artifact run bundle terminating in a Merkle root hash.
6. **Demonstrated GitHub CI Workflow**: Evaluated end-to-end on GitHub Actions with automated bot commits and structured PR audit comments.

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    subgraph INTAKE ["1. Intake & Assessment"]
        SPEC["UpgradeSpec<br/>(e.g. pydantic 1.10 -> 2.6)"] --> BASELINE["Baseline Sandbox Run<br/>(pytest captures failures)"]
        BASELINE --> GRAPH["AST Impact Graph<br/>(Imports, callers, test suites)"]
        GRAPH --> CLUSTER["Failure Clusters & Risk Map<br/>(Root-cause categorization)"]
    end

    subgraph RESEARCH ["2. Targeted Evidence"]
        CLUSTER --> TAVILY["Tavily Search API<br/>(Official changelogs & migration docs)"]
        TAVILY --> PACK["EvidencePack<br/>(Authoritative migration rules)"]
    end

    subgraph SYNTHESIS ["3. Synthesis & Safety Loop"]
        PACK --> NEMOTRON["NVIDIA Nemotron-3 Super 120B<br/>(Nebius Token Factory)"]
        NEMOTRON --> CAND["Candidate Patch<br/>(Surgically scoped diff)"]
        CAND --> SNAPSHOT["Atomic Snapshot Manager<br/>(Pre-patch SHA-256 tree hash)"]
        SNAPSHOT --> SANDBOX["Sandbox Verification<br/>(pytest + mypy strict)"]
    end

    subgraph RESOLUTION ["4. Verification & Delivery"]
        SANDBOX -- "Fail" --> ROLLBACK["Atomic Rollback<br/>(Restore byte-for-byte state)"]
        ROLLBACK --> NEG_FEEDBACK["Negative Feedback Loop<br/>(Synthesize Candidate n+1)"]
        NEG_FEEDBACK --> NEMOTRON
        SANDBOX -- "Pass" --> SEAL["Verification Contract Seal<br/>(All tests pass, 0 type errors)"]
        SEAL --> LEDGER["Chained SHA-256 Event Ledger<br/>(audit_manifest.json + 12 artifacts)"]
        LEDGER --> GITHUB["GitHub Action Runner<br/>(Bot commit + Verified PR #1)"]
    end

    style INTAKE fill:#0f172a,stroke:#334155,color:#fff
    style RESEARCH fill:#064e3b,stroke:#059669,color:#fff
    style SYNTHESIS fill:#1e1b4b,stroke:#4f46e5,color:#fff
    style RESOLUTION fill:#022c22,stroke:#10b981,color:#fff
```

---

## 🚀 Quickstart: Run in 60 Seconds

### Prerequisites
- Python 3.10+ (tested on Python 3.11, 3.12, 3.13, 3.14)
- Git & Virtual Environment

```bash
# Clone the repository
git clone https://github.com/ROSHAN0230/patchpilot-ci-demo.git patchpilot
cd patchpilot

# Set up virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 1. Run the Canonical End-to-End Live Demo
Execute the full **RED ➔ INVESTIGATE ➔ ATTEMPT 1 ➔ FAIL & ROLLBACK ➔ RECOVER (ATTEMPT 2) ➔ GREEN** lifecycle in real time:

```bash
python demo.py
```

*What this demonstrates:*
- Upgrades `pydantic` from `1.10.14` to `2.6.4`.
- Captures baseline test failures (`@validator` removed).
- Builds AST `ImpactGraph` and retrieves official V2 migration evidence via Tavily.
- Injects a syntax fault on Candidate 1 to exercise failure recovery.
- Sandbox fails ➔ **Atomic Snapshot Rollback** restores pristine disk state with SHA-256 byte-level verification (`True`).
- Synthesizes Candidate 2 ➔ Passes `pytest` 2/2 and `mypy` strict typecheck.
- Seals 12 cryptographic artifacts into `runs/canonical_live_demo/` with Merkle root hash.

### 2. Launch the Developer & Judge Observability Dashboard
Start the visual web dashboard to inspect timeline events, AST impact trees, diffs, and cryptographic seals:

```bash
python -m patchpilot.observability.cli --serve --port 8000
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser.

- **Live GitHub CI/CD Pull Request Demo**: [PR #1 — `chore(deps): Upgrade SQLAlchemy from 1.4.52 to 2.0.0`](https://github.com/ROSHAN0230/patchpilot-ci-demo/pull/1) (Autonomous recovery executed via [GitHub Actions Run #35993907979](https://github.com/ROSHAN0230/patchpilot-ci-demo/actions/runs/35993907979)).
- **Turnkey Public Web Demo (Render)**: Deploy the read-only observability dashboard to Render with 1 click using the included [`render.yaml`](https://render.com/deploy?repo=https://github.com/ROSHAN0230/patchpilot-ci-demo).

### 3. Run the Empirical Benchmark Suite
Inspect the 5 hard-gate benchmark scenarios and neutral competitor comparison:

```bash
python -m patchpilot.benchmarks.run_suite
```

---

## 📊 Empirical Benchmarks (5 Hard Gates)

All 5 benchmark scenarios were executed against live models (**NVIDIA Nemotron-3 Super 120B** on **Nebius Token Factory**) unassisted within the bounded candidate loop:

| Scenario ID | Dependency Jump | Baseline Failures | Target Files | Attempts / Rollbacks | Status | Runtime | Cost (USD, exact) |
|:---|:---|:---:|:---|:---:|:---:|:---:|:---:|
| `bm_scenario_1_single` | `pydantic 1.10.14 -> 2.6.4` | 2 fail | `models.py` | 1 att / 0 rb | **VERIFIED_GREEN** | 8.30s | **$0.001022** |
| `bm_scenario_2_multifile` | `pydantic 1.10.14 -> 2.6.4` | 2 fail | `core/config.py`, `core/schemas.py`, `services/user_service.py` | 3 att / 0 rb | **VERIFIED_GREEN** | 19.05s | **$0.003491** |
| `bm_scenario_3_adversarial` | `pydantic 1.10.14 -> 2.6.4` | 2 fail | `service_model.py` | 2 att / **1 rollback** | **VERIFIED_GREEN** | 8.78s | **$0.002294** |
| `bm_scenario_4_sqlalchemy` | `sqlalchemy 1.4.49 -> 2.0.28` | 2 fail | `models.py`, `repository.py` | 2 att / 0 rb | **VERIFIED_GREEN** | 17.36s | **$0.002570** |
| `bm_scenario_5_sqlalchemy_pristine` | `sqlalchemy 1.4.52 -> 2.0.54` | 2 fail | `models.py`, `repository.py` | 2 att / 0 rb | **VERIFIED_GREEN** | 21.92s | **$0.002429** |

- **Total Suite Cost (Exact)**: **$0.011806** (~**$0.0118**).
- **Average Cost per Migration**: **$0.00236** (~**$0.0024**).
- **Execution Backend**: `local_subprocess_isolated`.

---

## 🥊 Neutral Competitor Capability Comparison

| Evaluation Dimension | PatchPilot (Specialized) | General Coding Agents (SWE-bench / Devin-style) | Static Codemods (LibCST / Bowler) | Dependabot / Renovate |
|:---|:---|:---|:---|:---|
| **Remediation Accuracy & Context Strategy** | AST-grounded impact graph slice + targeted upstream migration retrieval | Direct whole-file or full-context prompt without dependency-aware impact graph | Rule-based syntax transformations (e.g. LibCST / Bowler) | Manifest version string update only |
| **Execution Safety & Rollback** | Bounded candidate loop with SHA-256 pre/post atomic snapshot rollback | In-place file generation; rollback requires external git intervention | Transactional file overwrite or operator-managed git revert | No application code modification; capability not exercised |
| **Migration Documentation Grounding** | Targeted retrieval of upstream migration guides and changelogs via search API | Parametric model knowledge; external retrieval depends on prompt/tools | Codified migration rules authored by library maintainers | Changelog links embedded in PR text; does not perform code remediation |
| **Auditability & Verification Contract** | Contract-enforced test & typecheck with SHA-256 chained event ledger & root hash | Conversational logs; verification requires external test runner | AST syntax validation; test suite execution requires separate CI step | Relies on downstream CI pipeline to evaluate opened PR |
| **Automated GitHub CI Workflow** | Automated bot commit with structured 8-section audit report posted to PR | Interactive developer environment or CLI; PR creation requires workflow integration | Batch CLI tool; requires separate CI workflow to commit | Automated PR creation triggered by registry releases |

---

## 🌐 Real-World CI Workflow Proof: GitHub Actions & PR #1

PatchPilot has been evaluated on a live GitHub repository and CI environment:

- **Repository**: [`ROSHAN0230/patchpilot-ci-demo`](https://github.com/ROSHAN0230/patchpilot-ci-demo)
- **Pull Request**: [PR #1 — `chore(deps): Upgrade SQLAlchemy from 1.4.52 to 2.0.0`](https://github.com/ROSHAN0230/patchpilot-ci-demo/pull/1)
  - **Head Branch**: `upgrade/sqlalchemy-2.0`
  - **Base Branch**: `main`
  - **Upgrade Target**: `sqlalchemy 1.4.52 -> >=2.0.0`
- **Bot Commit SHA**: [`83d9fc4a4805c87a5e88ee7ff96cf5d2cf57ea78`](https://github.com/ROSHAN0230/patchpilot-ci-demo/commit/83d9fc4a4805c87a5e88ee7ff96cf5d2cf57ea78)
- **GitHub Actions Workflow Run**: [`35993907979`](https://github.com/ROSHAN0230/patchpilot-ci-demo/actions/runs/35993907979) (Conclusion: `success`)

> **Note on Workflow Annotations:** The workflow run log contains a teardown warning in `Post Checkout PR Branch` (`The process '/usr/bin/git' failed with exit code 128`). This is a benign post-job cleanup occurrence in `actions/checkout@v4` during the initial PR #1 run caused by post-checkout git credential/ref cleanup after bot commits were pushed. The recovery job and overall workflow concluded with status `success`. The master repository action definitions have been updated to official Node 24 actions (`actions/checkout@v7`, `actions/setup-python@v7`, and `actions/github-script@v8`).

### Automated PR Comment Structure
Every PatchPilot PR comment includes a structured 8-section audit report:
1. **Upgrade Specification** (target package, old/new SemVer, manifest path).
2. **Impact Graph Summary** (affected symbols, dependent modules, test suites).
3. **Failure Clusters & Root Causes** (mapped to official deprecation categories).
4. **Evidence Pack & Citations** (exact URLs to official upstream docs).
5. **Candidate Lifecycle & Rollbacks** (number of attempts, duration, rollback events).
6. **Verification Contract Result** (test results, `mypy` strict typecheck, scope confinement).
7. **Audit Trail Manifest** (cryptographic SHA-256 root hash).
8. **Final Applied Diff**.

---

## 🔒 Security & Epistemic Truthfulness

We adhere to the highest standards of security engineering and truthful reporting:

- **Zero Secret Exposure**: Zero API keys or tokens in code, repository commits, test runs, telemetry files, or reports.
- **Compromised Credential Revocation**: Historical test tokens were explicitly revoked via GitHub unauthenticated revocation API (`POST https://api.github.com/credentials/revoke` ➔ HTTP 202).
- **Git Credential Manager (GCM)**: All Git interactions use native OS credential helpers without hardcoded tokens.
- **Execution Backend Truthfulness**: Current local sandbox execution is truthfully identified as `local_subprocess_isolated`. The containerized ConTree backend is gated as unavailable on the local Windows host.

---

## 📂 12 Sealed Run Artifacts

For every recovery run, PatchPilot seals 12 immutable artifacts inside `runs/<run_id>/`:
1. `audit_manifest.json` — Cryptographic manifest with root hash and metadata.
2. `upgrade_spec.json` — Migration target, SemVer jump, and constraints.
3. `impact_graph.json` — AST caller-callee dependency topology.
4. `failure_clusters.json` — Grouped failure root causes and exceptions.
5. `risk_map.json` — Semantic uncertainty index and risk regions.
6. `evidence_pack.json` — Tavily search queries, URLs, and documentation snippets.
7. `candidates.json` — Full history of generated candidates and rollback events.
8. `verification_contract.json` — Strict test and typecheck enforcement rules.
9. `verification_result.json` — Final seal with test pass rates and duration.
10. `recovery_history.json` — Sequential audit transitions.
11. `telemetry.jsonl` — Chained SHA-256 hash event log (`event[n].prev = event[n-1].hash`).
12. `final_diff.patch` — Unified diff applied to the repository.

---

## 🛠️ Technology Stack & Hackathon Alignment

- **Foundation Model**: `nvidia/nemotron-3-super-120b-a12b`
- **Inference Cloud**: **Nebius Token Factory** (high-throughput OpenAI-compatible API)
- **Web Search**: **Tavily AI Search API** (focused technical documentation search)
- **Static Analysis**: Python standard `ast` & symbol table visitors
- **Verification Engine**: `pytest`, `mypy`, `subprocess` isolation
- **Observability Server**: `FastAPI`, `Uvicorn`, Tailwind CSS Single-Page Dashboard
- **CLI & Output**: `Rich`, `argparse`

---

## ⚠️ Limitations & Future Work

- **Language Scope**: Python is our current production focus (covering `pydantic` and `sqlalchemy` migrations). The AST and impact graph architecture is language-agnostic and designed to extend to TypeScript (`@babel/parser`) and Rust (`syn`) in future releases.
- **Sandbox Isolation**: Current local execution relies on `local_subprocess_isolated`. Future iterations will enable hardware-isolated microVMs via ConTree drivers in cloud deployments.

---

*Built with precision for the NVIDIA × Nebius AI Hackathon 2026.*
