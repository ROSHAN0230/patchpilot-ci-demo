# PatchPilot Security Policy & Isolation Architecture

## 1. Overview & Threat Model

PatchPilot executes autonomous code remediation on repositories experiencing breaking changes from dependency upgrades. Because LLM-generated code and automated test execution involve running arbitrary code, PatchPilot implements explicit defense-in-depth isolation boundaries.

PatchPilot adheres strictly to **reality-based reporting**: we never claim hypervisor-level or containerized isolation when running under the isolated local subprocess backend.

---

## 2. Sandbox Backend Implementations

PatchPilot maintains two distinct sandbox drivers via the `SandboxDriver` interface:

| Backend Identifier | Type | Current Status | Capabilities |
| :--- | :--- | :--- | :--- |
| `local_subprocess_isolated` | Local Subprocess Sandbox | **Active / Production Default** | Sanitized env, credential stripping, process timeouts, filesystem boundaries, non-interactive execution |
| `contree_cloud_sandbox` | Cloud Container Sandbox | **Gated (Awaiting Provider Enablement)** | MicroVM / containerized tenant isolation (Nebius Token Factory Sandbox) |

---

## 3. Local Isolation Guarantees (`local_subprocess_isolated`)

When executing under `LocalSubprocessDriver`, the following guarantees are enforced:

### A. Credential Sanitization
* **Scrubbed Variables**: Subprocess execution environments are scrubbed of all API keys, access tokens, and secrets matching patterns:
  - `*API_KEY*`, `*SECRET*`, `*PASSWORD*`, `*TOKEN*`, `*AUTH*`, `*CREDENTIAL*`
  - `AWS_*`, `GITHUB_*`, `GH_*`, `SSH_*`
  - Specifically prevents exposure of `NEBIUS_API_KEY`, `TAVILY_API_KEY`, or developer credentials to executing tests or candidate patches.
* **Whitelisted Variables**: Only explicit runtime primitives (`PATH`, `SYSTEMROOT`, `TEMP`, `PYTHONPATH`, `VIRTUAL_ENV`) are forwarded.
* **Bytecode Isolation**: `PYTHONDONTWRITEBYTECODE=1` is enforced to prevent `.pyc` caching side effects across candidate rollbacks.

### B. Command Whitelisting & Pattern Blacklisting
* Dangerous shell invocation commands, remote downloaders, and reverse shell patterns (`rm -rf`, `curl`, `wget`, `nc`, `bash -i`, `cmd.exe /c del`) are intercepted and rejected prior to process spawning with `SecurityViolationError`.
* Execution uses `shell=False` exclusively with parameterized command arrays to eliminate shell-injection vectors.

### C. Filesystem Root Boundary Confinement
* Working directory execution is validated via canonical paths (`os.path.commonpath`).
* Any execution or file patch targeting paths outside the designated repository or temporary workspace boundary is rejected immediately.

### D. Process Timeout & Subprocess Cleanup
* All test and type-check commands are bound to strict wall-clock timeouts (default: 30 seconds).
* When a command exceeds the timeout, the subprocess tree is terminated, preventing hanging or infinite loops.

### E. Deterministic Workspaces & Cryptographic Rollback
* Each recovery execution operates in an isolated run directory.
* Pre-candidate state is hashed using SHA-256 composite tree hashes. If a patch fails verification, atomic rollback restores the repository to the exact pre-candidate bytes.

---

## 4. Current Limitations & What Local Isolation Does NOT Provide

To maintain absolute architectural honesty:
1. **Kernel/OS Isolation**: The local subprocess runs under the operating system permissions of the host user. It is not an OS-level chroot jail or Docker container.
2. **Network Isolation**: Local socket creation is not blocked at the OS firewall level; network prevention is handled via command stripping and process controls.
3. **Hardware Resource Limits**: CPU core pinning and memory limits are constrained by OS process groups rather than cgroups.

*When cloud container spawning via Nebius Token Factory / ConTree is enabled, network and filesystem isolation will be delegated to the remote container sandbox.*

---

## 5. Secret Hygiene, Historical Exposure & Remediation Posture

In strict adherence to reality-based engineering and transparent security disclosure:

1. **Historical Incident Disclosure**: A historical `.env` file containing development credentials was committed to repository history in the initial root commit (`f6d7cfe`) before being removed and untracked in commit `a03cf99`.
2. **Credential Invalidation & Rotation**: All credentials present in that historical commit (including Nebius Token Factory and Tavily API keys) were revoked upstream and rotated with newly issued credentials outside this chat.
3. **Current Working Tree Hygiene**: The active repository working tree and all tracked branches (`master`, `main`, `upgrade/sqlalchemy-2.0`) contain zero tracked `.env` files. `.env` is strictly ignored via `.gitignore`, and all CI workflows consume repository secrets exclusively.
4. **Intentional Preservation of Historical Git Objects**: Historical Git objects have been intentionally preserved rather than rewritten via destructive Git history filtering and force-pushing. This decision was made to maintain the integrity of live hackathon evaluation evidence—specifically GitHub Pull Request #1, the PatchPilot bot repair commit (`83d9fc4`), and GitHub Actions workflow run #35993907979—which would otherwise experience SHA drift, broken references, and detached CI run evidence.
5. **Preventive Secret Controls**:
   - **GitHub Secret Scanning & Push Protection**: Recommended to reject pushes containing known API key patterns at the remote gateway.
   - **Subprocess Environment Sanitization**: `SandboxSecurityPolicy.sanitize_environment` scrubs all credential patterns from subprocess environments before executing candidate repairs or test suites.
   - **Automated Hygiene Verification**: Automated repository tests enforce that `.env` remains untracked and that no secret literals enter tracked files.
