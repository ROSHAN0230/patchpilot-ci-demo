# PatchPilot: 3-Minute YouTube Demo Video Script 🎬
**Hackathon:** NVIDIA × Nebius AI Hackathon 2026  
**Track:** Coding & Agentic Engineering  
**Target Duration:** 2 minutes 45 seconds (Max 3:00)

---

### ⏱️ Timestamp Breakdown

| Timestamp | Segment Title | Screen Visual | Audio / Voiceover Script |
|:---|:---|:---|:---|
| **0:00 - 0:25** | **The Hook & Problem** | Screen recording of a standard Dependabot / Renovate PR with failing CI checks (`pytest: 2 failed`). | *"Every software team faces friction during major dependency upgrades. Automated version bumpers modify package version strings in pyproject.toml, leaving developers to diagnose breaking changes, failing tests, and API deprecations manually. Unconstrained coding assistants often edit files without dependency-aware impact analysis or rollback guarantees. PatchPilot explores a specialized alternative: an autonomous breaking-change recovery workflow."* |
| **0:25 - 0:55** | **Introducing PatchPilot** | Transition to PatchPilot Architecture Mermaid Diagram in README / Dashboard. Highlight NVIDIA Nemotron-3 Super 120B on Nebius Token Factory and Tavily Docs Search. | *"Meet PatchPilot: an autonomous breaking-change recovery and dependency upgrade engineer. PatchPilot constructs an AST-grounded Impact Graph to locate affected symbols, dependent modules, and test suites. Next, it retrieves official upstream documentation and migration changelogs via the Tavily Search API. Then, it uses NVIDIA Nemotron-3 Super 120B on Nebius Token Factory to synthesize bounded candidate patches using targeted context slices."* |
| **0:55 - 1:40** | **The Canonical Live Demo (`python demo.py`)** | Terminal split screen. Running `python demo.py`. Rich terminal output showing: Stage 1 Breaking Baseline, Stage 2 AST Graph, Stage 3 Candidate 1, Stage 4 Sandbox Fail & Atomic Rollback, Stage 5 Candidate 2 Recovery, Stage 6 Sealed Artifacts. | *"Let's see it live. Here, we run `python demo.py` upgrading Pydantic from v1 to v2. Notice the progression:*<br/>*1. Baseline runs: pytest captures breaking changes in validator decorators.*<br/>*2. PatchPilot maps the AST dependency graph and retrieves official V2 migration rules.*<br/>*3. To verify safety, watch what happens when Candidate 1 encounters an intentional syntax fault: the sandbox catches the failure, halts, and immediately triggers an Atomic Snapshot Rollback. The pre-patch and post-rollback SHA-256 byte hashes match identically.*<br/>*4. Armed with negative feedback, PatchPilot synthesizes Candidate 2. Pytest passes 2/2 green, strict typechecks pass, and the verification contract is satisfied."* |
| **1:40 - 2:15** | **Developer Observability Dashboard** | Browser opens to `http://localhost:8000`. Demonstrating the timeline, candidate diff viewer, impact graph, and cryptographic audit seal. | *"Every recovery run produces 12 immutable artifacts. In our local Observability Dashboard, developers and judges can audit the entire execution timeline. Notice the Cryptographic Audit Seal: every event is hashed against its predecessor in an immutable SHA-256 chain, terminating in a verifiable Merkle root hash for auditability."* |
| **2:15 - 2:40** | **Real GitHub Actions & PR Proof** | Switch to browser showing GitHub PR: `https://github.com/ROSHAN0230/patchpilot-ci-demo/pull/1` and Actions run `#35993907979`. | *"Here is real-world proof running in GitHub Actions on repository `ROSHAN0230/patchpilot-ci-demo`. Workflow run 35993907979 succeeded green, committed the verified fix as a bot commit on branch upgrade/sqlalchemy-2.0, and posted a structured 8-section audit report directly into Pull Request #1."* |
| **2:40 - 3:00** | **Benchmarks & Conclusion** | Terminal showing `python -m patchpilot.benchmarks.run_suite` benchmark table and final slide. | *"Across 5 hard-gate benchmark scenarios—including multi-file refactors, adversarial traps, and pristine SQLAlchemy migrations—PatchPilot verified all 5 scenarios green with an average cost of $0.0024 per run (total suite cost: $0.0118).*<br/><br/>*PatchPilot demonstrates how specialized dependency-aware architectures bring predictability to automated software maintenance. Thank you!"* |

---

### 🎙️ Voiceover Recording Tips
- **Pacing**: Speak at an energetic, confident, conversational 140–150 words per minute.
- **Microphone**: Use a clear USB condenser microphone with pop filter.
- **Video Resolution**: 1080p or 4K, 60fps, dark mode terminal and browser.
- **Zoom Level**: 125% in Chrome and 18pt font in terminal so code is crisp on mobile screens.
