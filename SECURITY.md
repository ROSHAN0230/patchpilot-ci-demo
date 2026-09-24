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
