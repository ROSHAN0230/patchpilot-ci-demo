"""
PatchPilot Hard Gate 2: End-to-End Autonomous Repair Engine.
Executes: FAIL -> RESEARCH (Tavily) -> REASON (Nemotron on Nebius) -> PATCH -> SANDBOX (ConTree/Local) -> RE-TEST -> PASS.
"""

import os
import sys
import time
import subprocess
import re
from typing import Dict, Any, Optional, Tuple
from dotenv import load_dotenv

# Load .env if present
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

class PatchPilotPOC:
    def __init__(self, repo_dir: str):
        self.repo_dir = os.path.abspath(repo_dir)
        self.nebius_key = os.environ.get("NEBIUS_API_KEY", "").strip()
        self.tavily_key = os.environ.get("TAVILY_API_KEY", "").strip()
        self.project_id = os.environ.get("NEBIUS_PROJECT_ID", "").strip()
        self.python_bin = sys.executable

        # Verified models
        self.primary_model = "nvidia/nemotron-3-super-120b-a12b"
        self.backup_model = "nebius/nvidia/nemotron-3-super-120b-a12b"
        self.active_model = self.primary_model

        # Telemetry metrics
        self.telemetry = {
            "model_used": self.active_model,
            "sandbox_used": "Pending",
            "iterations": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "model_latency_ms": 0.0,
            "tavily_latency_ms": 0.0,
            "sandbox_time_ms": 0.0,
            "tests_before": "FAIL",
            "tests_after": "PENDING",
            "tavily_sources": [],
            "estimated_cost_usd": 0.0,
        }

    def run_tests_local(self) -> Tuple[int, str]:
        """Runs pytest on the target repository locally."""
        t0 = time.time()
        cmd = [self.python_bin, "-m", "pytest", "test_models.py", "-v"]
        result = subprocess.run(
            cmd,
            cwd=self.repo_dir,
            capture_output=True,
            text=True,
        )
        elapsed = (time.time() - t0) * 1000
        self.telemetry["sandbox_time_ms"] += elapsed
        output = result.stdout + "\n" + result.stderr
        return result.returncode, output

    def run_tests_contree(self) -> Optional[Tuple[int, str]]:
        """Executes test suite inside real Nebius ConTree Sandbox if available."""
        if not self.nebius_key:
            return None
        try:
            from contree_sdk import ContreeSync
            from contree_sdk.config import ContreeConfig
            from contree_sdk.auth import IAMAuth

            auth = IAMAuth(token=self.nebius_key, project_id=self.project_id)
            config = ContreeConfig(auth=auth)
            client = ContreeSync(config=config)
            # Verify token validity
            client.get_token_info()

            # Read files to transfer
            with open(os.path.join(self.repo_dir, "models.py"), "r", encoding="utf-8") as f:
                models_code = f.read()
            with open(os.path.join(self.repo_dir, "test_models.py"), "r", encoding="utf-8") as f:
                test_code = f.read()

            t0 = time.time()
            image = client.images.use("ubuntu:latest")
            proc = image.run(
                shell="pip install -q pytest pydantic && python3 -m pytest test_models.py -v",
                files={"models.py": models_code, "test_models.py": test_code},
            )
            proc.wait()
            elapsed = (time.time() - t0) * 1000
            self.telemetry["sandbox_time_ms"] += elapsed
            self.telemetry["sandbox_used"] = "Nebius Token Factory Sandbox (ConTree Cloud)"
            output = f"{proc.stdout}\n{proc.stderr}"
            return proc.returncode, output

        except Exception as e:
            print(f"[ConTree Sandbox Status]: {e}")
            return None

    def execute_sandbox(self) -> Tuple[int, str]:
        """Routes execution to ConTree Cloud Sandbox or Local Subprocess Sandbox."""
        contree_res = self.run_tests_contree()
        if contree_res is not None:
            return contree_res
        self.telemetry["sandbox_used"] = "Local Subprocess Sandbox (Fallback)"
        return self.run_tests_local()

    def parse_failure(self, test_output: str) -> Dict[str, str]:
        """Deterministically extracts failing file, line, and specific exception."""
        # Check for PydanticUserError or PydanticImportError
        pydantic_err = re.search(r"(pydantic\.errors\.\w+:\s+[^\n]+)", test_output)
        
        # Check for Pytest 'E   ...' lines
        e_lines = [l.strip()[4:] for l in test_output.splitlines() if l.strip().startswith("E   ")]
        
        # Check for deprecation notices
        dep_matches = re.findall(r"(PydanticDeprecatedSince20:\s+[^\n]+)", test_output)
        
        if pydantic_err:
            error_msg = pydantic_err.group(1)
        elif e_lines:
            error_msg = e_lines[0]
        else:
            error_msg = "Pydantic V2 migration incompatibility"

        dep_notes = " | ".join(dep_matches[:3]) if dep_matches else ""

        target_file = "models.py"
        target_path = os.path.join(self.repo_dir, target_file)

        return {
            "target_file": target_file,
            "target_path": target_path,
            "error_msg": error_msg,
            "deprecation_notes": dep_notes,
            "raw_output": test_output[-2000:],
        }

    def fetch_migration_docs_tavily(self, error_msg: str) -> str:
        """Executes real Tavily search for authoritative migration guidance."""
        clean_err = re.sub(r"[^\w\s-]", " ", error_msg[:100])
        query = f"Pydantic V2 migration guide {clean_err}"
        print(f"\n[Tavily] Executing real search: '{query}'...")

        if not self.tavily_key:
            print("[Tavily] Key not set. Cannot perform real search.")
            raise RuntimeError("TAVILY_API_KEY required for Hard Gate 2.")

        from tavily import TavilyClient
        t0 = time.time()
        tavily = TavilyClient(api_key=self.tavily_key)
        res = tavily.search(query=query, search_depth="basic", max_results=2)
        elapsed = (time.time() - t0) * 1000
        self.telemetry["tavily_latency_ms"] += elapsed

        snippets = []
        for r in res.get("results", []):
            url = r.get("url", "")
            title = r.get("title", "")
            self.telemetry["tavily_sources"].append(url)
            snippets.append(f"Source [{title}] ({url}):\n{r.get('content')}")

        docs = "\n\n".join(snippets)
        print(f"[Tavily] Retrieved {len(snippets)} live sources ({elapsed:.1f}ms).")
        return docs

    def query_nemotron_nebius(self, current_code: str, failure: Dict[str, str], docs: str) -> str:
        """Executes real inference call to Nemotron-3 on Nebius Token Factory."""
        import requests

        system_prompt = (
            "You are a principal software engineer refactoring a Python repository from Pydantic V1 to Pydantic V2.\n"
            "Rules:\n"
            "1. Fix the breaking change identified in the test output.\n"
            "2. Preserve all existing business logic, validation behavior, and function signatures.\n"
            "3. Output ONLY the complete valid Python code for the file inside a single ```python ... ``` block.\n"
            "4. Do not output any markdown or explanations outside the code block."
        )

        user_content = f"""File: {failure['target_file']}

CURRENT CODE:
```python
{current_code}
```

TEST FAILURE:
{failure['error_msg']}

WARNINGS:
{failure['deprecation_notes']}

OFFICIAL UPSTREAM MIGRATION DOCS (RETRIEVED VIA TAVILY):
{docs}

Provide the updated code for {failure['target_file']} that resolves this failure while maintaining exact behavior."""

        print(f"\n[Nebius] Calling {self.active_model} on Token Factory...")
        t0 = time.time()

        headers = {
            "Authorization": f"Bearer {self.nebius_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.active_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.05,
            "max_tokens": 3000,
        }

        url = "https://api.tokenfactory.nebius.com/v1/chat/completions"
        resp = requests.post(url, headers=headers, json=payload, timeout=50)

        # Fallback to alternate ID if catalog prefix differs
        if resp.status_code != 200 and self.active_model == self.primary_model:
            print(f"[Nebius] Model ID '{self.primary_model}' returned {resp.status_code}. Retrying with '{self.backup_model}'...")
            payload["model"] = self.backup_model
            self.active_model = self.backup_model
            self.telemetry["model_used"] = self.active_model
            resp = requests.post(url, headers=headers, json=payload, timeout=50)

        elapsed = (time.time() - t0) * 1000
        self.telemetry["model_latency_ms"] += elapsed

        if resp.status_code != 200:
            raise RuntimeError(f"Nebius Token Factory call failed (HTTP {resp.status_code}): {resp.text}")

        data = resp.json()
        usage = data.get("usage", {})
        self.telemetry["input_tokens"] += usage.get("prompt_tokens", 0)
        self.telemetry["output_tokens"] += usage.get("completion_tokens", 0)

        # Estimate costs based on 120B MoE tier
        self.telemetry["estimated_cost_usd"] += (
            (usage.get("prompt_tokens", 0) * 0.0008 / 1000.0) +
            (usage.get("completion_tokens", 0) * 0.002 / 1000.0)
        )

        msg_obj = data["choices"][0]["message"]
        content = (msg_obj.get("content") or msg_obj.get("reasoning") or "").strip()
        print(f"[Nebius] Generated patch in {elapsed:.1f}ms (Tokens: {usage.get('completion_tokens', 0)}).")
        return content

    def extract_code(self, response_text: str) -> str:
        # Match python code blocks first
        match = re.search(r"```python\s*\n(.*?)\n```", response_text, re.DOTALL)
        if not match:
            match = re.search(r"```\s*\n(.*?)\n```", response_text, re.DOTALL)
        if match:
            return match.group(1).strip() + "\n"
        return response_text.strip() + "\n"

    def execute_closed_loop(self, max_turns: int = 3) -> bool:
        print("\n" + "#" * 65)
        print("  PATCHPILOT: HARD GATE 2 - LIVE END-TO-END REPAIR EXECUTION")
        print("#" * 65)

        # Step 1: Run baseline pytest
        print("\n[*] Initial test run on unmodified repository...")
        rc_initial, out_initial = self.execute_sandbox()
        if rc_initial == 0:
            print("[NOTE] All tests already pass. Resetting models.py to baseline failure.")
            return False

        print(f"[TESTS BEFORE]: FAILED (Exit code: {rc_initial})")
        self.telemetry["tests_before"] = f"FAILED (Exit Code {rc_initial})"

        target_path = os.path.join(self.repo_dir, "models.py")
        with open(target_path, "r", encoding="utf-8") as f:
            original_code = f.read()

        current_code = original_code
        last_test_output = out_initial

        for turn in range(1, max_turns + 1):
            self.telemetry["iterations"] = turn
            print(f"\n" + "=" * 50)
            print(f"  REPAIR TURN {turn} OF {max_turns}")
            print("=" * 50)

            # Step 2: Parse failure
            failure = self.parse_failure(last_test_output)
            print(f"[*] Target File   : {failure['target_file']}")
            print(f"[*] Parsed Failure: {failure['error_msg'][:110]}")

            # Step 3: Real Tavily doc retrieval
            docs = self.fetch_migration_docs_tavily(failure["error_msg"])

            # Step 4: Real Nebius Nemotron call
            try:
                raw_patch = self.query_nemotron_nebius(current_code, failure, docs)
                patched_code = self.extract_code(raw_patch)
            except Exception as e:
                print(f"[ERROR] Inference turn failed: {e}")
                print("[*] Performing rollback to original code.")
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(original_code)
                return False

            # Step 5: Apply patch
            print(f"[*] Applying patch to {failure['target_file']}...")
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(patched_code)

            # Step 6: Sandbox re-test
            print(f"[*] Executing test suite inside {self.telemetry['sandbox_used']}...")
            rc_after, out_after = self.execute_sandbox()

            if rc_after == 0:
                print(f"\n[PASS] All tests passed green on turn {turn}!")
                self.telemetry["tests_after"] = "PASSED (100% Green)"
                self.print_summary(patched_code)
                return True
            else:
                print(f"[WARN] Tests still failing after turn {turn} (Exit code: {rc_after}).")
                # Advance context for next turn
                last_test_output = out_after
                current_code = patched_code

        print("\n[FAIL] Exceeded maximum turns without achieving 100% pass.")
        print("[*] Rolling back models.py to original state.")
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(original_code)
        self.telemetry["tests_after"] = "FAILED"
        self.print_summary(current_code)
        return False

    def print_summary(self, final_code: str):
        print("\n" + "=" * 65)
        print("  PATCHPILOT REAL EXECUTION REPORT & TELEMETRY")
        print("=" * 65)
        print(f"Model Used        : {self.telemetry['model_used']}")
        print(f"Sandbox Used      : {self.telemetry['sandbox_used']}")
        print(f"Iterations        : {self.telemetry['iterations']}")
        print(f"Tests Before      : {self.telemetry['tests_before']}")
        print(f"Tests After       : {self.telemetry['tests_after']}")
        print(f"Input Tokens      : {self.telemetry['input_tokens']}")
        print(f"Output Tokens     : {self.telemetry['output_tokens']}")
        print(f"Model Latency     : {self.telemetry['model_latency_ms']:.1f} ms")
        print(f"Tavily Latency    : {self.telemetry['tavily_latency_ms']:.1f} ms")
        print(f"Sandbox Time      : {self.telemetry['sandbox_time_ms']:.1f} ms")
        print(f"Est. Token Cost   : ${self.telemetry['estimated_cost_usd']:.5f}")
        print("Tavily Sources    :")
        for s in set(self.telemetry["tavily_sources"]):
            print(f"  - {s}")
        print("-" * 65)
        print("FINAL PATCHED models.py:")
        print("-" * 65)
        print(final_code.strip())
        print("=" * 65 + "\n")

if __name__ == "__main__":
    repo = os.path.join(os.path.dirname(__file__), "sample_repo")
    agent = PatchPilotPOC(repo_dir=repo)
    success = agent.execute_closed_loop()
    sys.exit(0 if success else 1)
