# PatchPilot: 3-Minute YouTube Demo Video Script 🎬
**Hackathon:** NVIDIA × Nebius AI Hackathon 2026  
**Track:** Coding & Agentic Engineering  
**Target Duration:** 2 minutes 45 seconds (Max 3:00)

---

### ⏱️ Timestamp Breakdown

| Timestamp | Segment Title | Screen Visual | Audio / Voiceover Script |
|:---|:---|:---|:---|
| **0:00 - 0:25** | **The Hook & Problem** | Screen recording of a standard Dependabot / Renovate PR with failing red CI checks (`pytest: 2 failed`). | *"Every software team fears major dependency upgrades. Tools like Dependabot merely bump a version number in pyproject.toml and leave you with a broken pull request, failing tests, and hours of tedious migration work. Meanwhile, general coding agents dump 50,000 tokens of raw code into prompts, hallucinate deprecated syntax, and make things worse. What if dependency maintenance wasn't just a version bump, but autonomous breaking-change recovery?"* |
| **0:25 - 0:55** | **Introducing PatchPilot** | Transition to PatchPilot Architecture Mermaid Diagram in README / Dashboard. Highlight NVIDIA Nemotron-3 Super 120B on Nebius Token Factory and Tavily Docs Search. | *"Meet PatchPilot: the autonomous breaking-change recovery and dependency upgrade engineer. PatchPilot doesn't guess. It first builds an AST-grounded Impact Graph to locate all affected symbols and callers. Next, it queries Tavily Search for authoritative upstream documentation and changelogs. Then, it uses NVIDIA Nemotron-3 Super 120B on Nebius Token Factory to generate surgical patches—costing less than a third of a cent per run."* |
| **0:55 - 1:40** | **The Canonical Live Demo (`python demo.py`)** | Terminal split screen. Running `python demo.py`. Rich terminal output showing: Stage 1 Breaking Baseline, Stage 2 AST Graph, Stage 3 Candidate 1, Stage 4 Sandbox Fail & Atomic Rollback, Stage 5 Candidate 2 Recovery, Stage 6 Sealed Artifacts. | *"Let's see it live. Here, we run `python demo.py` upgrading Pydantic from v1 to v2. Notice the progression:*<br/>*1. Baseline runs: pytest catches breaking changes in validator decorators.*<br/>*2. PatchPilot maps the AST dependency graph and pulls official V2 migration rules.*<br/>*3. To prove safety, watch what happens when Candidate 1 makes a mistake: the sandbox catches the failure, halts, and immediately triggers an Atomic Snapshot Rollback. The pre-patch and post-rollback SHA-256 byte hashes match perfectly: zero file corruption!*<br/>*4. Armed with negative feedback, PatchPilot synthesizes Candidate 2. Pytest passes 2/2 green, typechecks pass, and the contract is sealed!"* |
| **1:40 - 2:15** | **Developer Observability Dashboard** | Browser opens to `http://localhost:8000`. Demonstrating the timeline, candidate diff viewer, impact graph, and cryptographic audit seal. | *"Every recovery run produces 12 immutable artifacts. Here in our local Observability Dashboard, developers and judges can audit the entire execution timeline. Notice the Cryptographic Audit Seal: every event is hashed against its predecessor in an immutable SHA-256 chain, terminating in a verifiable Merkle root hash. You get complete tamper-resistance and replayability."* |
| **2:15 - 2:40** | **Real GitHub Actions & PR Proof** | Switch to browser showing GitHub PR: `https://github.com/ROSHAN0230/patchpilot-ci-demo/pull/1` and Actions run `#35993907979`. | *"This isn't a mock or local-only script. Here is real-world proof running in GitHub Actions on repository `ROSHAN0230/patchpilot-ci-demo`. Workflow run 35993907979 succeeded green, committed the surgical fix as a bot commit, and posted a complete 8-section audit report directly into Pull Request #1."* |
| **2:40 - 3:00** | **Benchmarks & Conclusion** | Terminal showing `python -m patchpilot.benchmarks.run_suite` benchmark table and final slide. | *"Across 5 hard-gate benchmark scenarios—including multi-file refactors, adversarial traps, and pristine SQLAlchemy 2.0 migrations—PatchPilot achieved 100% green verification for an average cost of $0.002 per run.*<br/><br/>*PatchPilot turns dependency upgrades from a dreaded maintenance tax into a solved, autonomous background process. Thank you!"* |

---

### 🎙️ Voiceover Recording Tips
- **Pacing**: Speak at an energetic, confident, conversational 140–150 words per minute.
- **Microphone**: Use a clear USB condenser microphone with pop filter.
- **Video Resolution**: 1080p or 4K, 60fps, dark mode terminal and browser.
- **Zoom Level**: 125% in Chrome and 18pt font in terminal so code is crisp on mobile screens.
