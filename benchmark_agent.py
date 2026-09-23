"""
PatchPilot Multi-Iteration Benchmark Agent (Hard Gate 2.5 & 2.6).
Demonstrates sequential multi-turn remediation across multiple repository files.
"""

import os
import sys
import re
import time
import argparse
import subprocess
import requests
from typing import Dict, Any, List, Tuple, Optional
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

class BenchmarkAgent:
    def __init__(self, backend: str = "contree"):
        self.repo_dir = os.path.join(os.path.dirname(__file__), "benchmark_repo")
        self.backend = backend  # "contree" or "local"
        self.nebius_key = os.environ.get("NEBIUS_API_KEY", "").strip()
        self.tavily_key = os.environ.get("TAVILY_API_KEY", "").strip()
        self.project_id = os.environ.get("NEBIUS_PROJECT_ID", "").strip()
        self.python_bin = sys.executable
        self.model_id = "nvidia/nemotron-3-super-120b-a12b"

        self.telemetry = {
            "backend": self.backend,
            "model_id": self.model_id,
            "total_iterations": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "iterations_log": [],
        }

    def run_tests_local(self) -> Tuple[int, str, float]:
        t0 = time.time()
        cmd = [self.python_bin, "-m", "pytest", "tests/test_suite.py", "-v", "-x"]
        result = subprocess.run(
            cmd,
            cwd=self.repo_dir,
            capture_output=True,
            text=True,
        )
        elapsed = (time.time() - t0) * 1000
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        return result.returncode, output, elapsed

    def run_tests_contree(self) -> Tuple[int, str, float]:
        if not self.nebius_key or not self.project_id:
            raise RuntimeError("ConTree requires NEBIUS_API_KEY and NEBIUS_PROJECT_ID")

        from contree_sdk import ContreeSync
        from contree_sdk.config import ContreeConfig
        from contree_sdk.auth import IAMAuth

        auth = IAMAuth(token=self.nebius_key, project_id=self.project_id)
        config = ContreeConfig(auth=auth)
        client = ContreeSync(config=config)

        # Probe token
        info = client.get_token_info()
        if not info.permissions.get("spawn", False):
            raise PermissionError(
                f"ConTree token {info.token_uuid} has spawn=False. Account lacks sandbox creation permission. Limits: {info.limits}"
            )

        # Upload repository files as bytes
        files_to_upload = {}
        for root, _, files in os.walk(self.repo_dir):
            for f in files:
                if f.endswith(".py"):
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, self.repo_dir).replace("\\", "/")
                    with open(full_p, "rb") as fp:
                        files_to_upload[f"/app/{rel_p}"] = fp.read()

        t0 = time.time()
        image = client.images.use("python:3.11-slim")
        proc = image.run(
            shell="cd /app && pip install -q pytest pydantic && python3 -m pytest tests/test_suite.py -v -x",
            files=files_to_upload,
        )
        proc.wait()
        elapsed = (time.time() - t0) * 1000
        output = f"{proc.stdout}\n{proc.stderr}"
        return proc.returncode, output, elapsed

    def execute_sandbox(self) -> Tuple[int, str, float]:
        if self.backend == "contree":
            return self.run_tests_contree()
        else:
            return self.run_tests_local()

    def parse_test_failure(self, test_output: str) -> Dict[str, str]:
        """Extracts the first failing repository file, line, and error from pytest output."""
        failing_file = None

        # Scan for known repository source files involved in failure
        repo_files = []
        for root, _, files in os.walk(self.repo_dir):
            for f in files:
                if f.endswith(".py") and f != "test_suite.py":
                    rel = os.path.relpath(os.path.join(root, f), self.repo_dir).replace("\\", "/")
                    repo_files.append(rel)

        for line in test_output.splitlines():
            # Skip python internal / pytest frames
            if "site-packages" in line or ".venv" in line or "_pytest" in line:
                continue
            for rf in repo_files:
                if rf in line.replace("\\", "/"):
                    failing_file = rf
                    break
            if failing_file:
                break

        # Fallback priority if pytest caught error during collection/assertion
        if not failing_file:
            if "core/config.py" in test_output or "TagList" in test_output or "RootModel" in test_output or "__root__" in test_output:
                failing_file = "core/config.py"
            elif "core/schemas.py" in test_output or "AccountPayload" in test_output or "regex" in test_output:
                failing_file = "core/schemas.py"
            elif "services/user_service.py" in test_output or "UserDTO" in test_output or "from_orm" in test_output:
                failing_file = "services/user_service.py"
            else:
                failing_file = repo_files[0] if repo_files else "core/config.py"

        # Extract primary error message
        e_lines = re.findall(r"^E\s+(.+)$", test_output, re.MULTILINE)
        error_msg = e_lines[0].strip() if e_lines else "Pydantic migration incompatibility"

        # Extract relevant deprecation warnings
        warnings = re.findall(r"(PydanticDeprecatedSince20:[^\n]+)", test_output)
        warn_str = " | ".join(warnings[:2]) if warnings else ""

        full_path = os.path.join(self.repo_dir, failing_file)
        return {
            "rel_file": failing_file,
            "abs_path": full_path,
            "error_msg": error_msg,
            "warnings": warn_str,
        }

    def search_docs_tavily(self, error_msg: str) -> Tuple[str, str, str]:
        clean_err = re.sub(r"[^\w\s-]", " ", error_msg[:90]).strip()
        query = f"Pydantic V2 migration guide {clean_err}"
        
        from tavily import TavilyClient
        t0 = time.time()
        client = TavilyClient(api_key=self.tavily_key)
        res = client.search(query=query, search_depth="basic", max_results=2)
        elapsed = (time.time() - t0) * 1000

        results = res.get("results", [])
        top_url = results[0].get("url", "unknown") if results else "none"
        top_title = results[0].get("title", "Pydantic V2 Docs") if results else "none"

        snippets = [f"Source [{r.get('title')}] ({r.get('url')}):\n{r.get('content')}" for r in results]
        docs = "\n\n".join(snippets)
        return docs, top_url, top_title

    def synthesize_patch_nemotron(self, file_path: str, rel_file: str, error_msg: str, warnings: str, docs: str) -> Tuple[str, Dict[str, Any]]:
        with open(file_path, "r", encoding="utf-8") as f:
            original_code = f.read()

        system_prompt = (
            "You are a principal Python systems architect upgrading a production codebase from Pydantic V1 to Pydantic V2.\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. Keep internal reasoning concise.\n"
            "2. Fix the specific error and deprecation warnings reported for the file.\n"
            "3. Preserve all existing business logic, validation semantics, type hints, and function signatures.\n"
            "4. Output the complete updated Python code for the file inside a single ```python ... ``` code block.\n"
            "5. Do NOT output any conversational text or explanations outside the code block."
        )

        user_content = f"""TARGET FILE: {rel_file}

CURRENT CODE:
```python
{original_code}
```

PYTEST FAILURE:
{error_msg}

ACTIVE DEPRECATIONS:
{warnings}

AUTHORITATIVE UPSTREAM MIGRATION DOCS (RETRIEVED VIA TAVILY):
{docs[:1500]}

Provide the complete updated Python code for {rel_file} that resolves this failure completely."""

        headers = {
            "Authorization": f"Bearer {self.nebius_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.0,
            "max_tokens": 4000,
            "reasoning_effort": "low",
        }

        t0 = time.time()
        resp = requests.post("https://api.tokenfactory.nebius.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
        elapsed = (time.time() - t0) * 1000

        if resp.status_code != 200:
            raise RuntimeError(f"Nemotron inference failed: HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        usage = data.get("usage", {})
        inp_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        cost = (inp_tok * 0.0008 / 1000.0) + (out_tok * 0.002 / 1000.0)

        msg = data["choices"][0]["message"]
        content = (msg.get("content") or "").strip()
        reasoning = (msg.get("reasoning") or "").strip()

        # Extract code block from content or reasoning
        match = re.search(r"```python\s*\n(.*?)\n```", content, re.DOTALL)
        if not match:
            match = re.search(r"```\s*\n(.*?)\n```", content, re.DOTALL)
        if not match and reasoning:
            match = re.search(r"```python\s*\n(.*?)\n```", reasoning, re.DOTALL)
        if not match and reasoning:
            match = re.search(r"```\s*\n(.*?)\n```", reasoning, re.DOTALL)

        if not match:
            raise ValueError(f"Model did not return a valid python code block. Content length: {len(content)}, Reasoning length: {len(reasoning)}")
            
        clean_code = match.group(1).strip() + "\n"

        meta = {
            "latency_ms": elapsed,
            "input_tokens": inp_tok,
            "output_tokens": out_tok,
            "cost_usd": cost,
        }
        return clean_code, meta

    def run_remediation(self, max_turns: int = 5) -> bool:
        print("\n" + "=" * 70)
        print("  PATCHPILOT: AUTONOMOUS MULTI-ITERATION BENCHMARK REMEDIATION")
        print(f"  Target Repository : benchmark_repo")
        print(f"  Execution Backend : {self.backend.upper()}")
        print(f"  Reasoning Model   : {self.model_id}")
        print("=" * 70)

        # Baseline execution
        print("\n[TEST] Running initial test suite...")
        try:
            rc, out, dur = self.execute_sandbox()
        except Exception as e:
            print(f"[SANDBOX EXECUTION FAILED]: {type(e).__name__}: {e}")
            if self.backend == "contree":
                print("\n[STOP] ConTree execution backend failed as configured. Halting per strict gate rules.")
                return False
            raise e

        if rc == 0:
            print("[VERIFIED] All tests already pass. No remediation needed.")
            return True

        print(f"[TESTS BEFORE]: FAILED (Exit Code {rc}) in {dur:.1f}ms")

        turn = 0
        while turn < max_turns:
            turn += 1
            print(f"\n" + "-" * 50)
            print(f" ITERATION {turn} OF {max_turns}")
            print("-" * 50)

            # Step 1: Diagnose
            failure = self.parse_test_failure(out)
            print(f"[FAILURE DETECTED]")
            print(f"  Target File : {failure['rel_file']}")
            print(f"  Error Detail: {failure['error_msg'][:110]}")

            # Step 2: Doc Search via Tavily
            print(f"[DOC SEARCH] Querying upstream documentation via Tavily...")
            docs, source_url, source_title = self.search_docs_tavily(failure['error_msg'])
            print(f"  Source Title: {source_title}")
            print(f"  Source URL  : {source_url}")

            # Step 3: Model reasoning & synthesis
            print(f"[MODEL ANALYSIS] Prompting {self.model_id} on Nebius Token Factory...")
            patched_code, meta = self.synthesize_patch_nemotron(
                file_path=failure['abs_path'],
                rel_file=failure['rel_file'],
                error_msg=failure['error_msg'],
                warnings=failure['warnings'],
                docs=docs,
            )
            print(f"  Latency     : {meta['latency_ms']:.1f}ms")
            print(f"  Tokens      : {meta['input_tokens']} in / {meta['output_tokens']} out")
            print(f"  Cost        : ${meta['cost_usd']:.5f}")

            # Step 4: Apply Patch
            print(f"[PATCH] Writing synthesized code to {failure['rel_file']}...")
            with open(failure['abs_path'], "w", encoding="utf-8") as f:
                f.write(patched_code)

            # Step 5: Sandbox Execution & Retest
            print(f"[SANDBOX EXECUTION] Running pytest inside {self.backend.upper()} sandbox...")
            rc, out, dur = self.execute_sandbox()
            print(f"[RETEST] Exit code: {rc} (Sandbox time: {dur:.1f}ms)")

            iteration_record = {
                "iteration": turn,
                "target_file": failure['rel_file'],
                "error_encountered": failure['error_msg'],
                "tavily_source": source_url,
                "model_latency_ms": meta['latency_ms'],
                "input_tokens": meta['input_tokens'],
                "output_tokens": meta['output_tokens'],
                "cost_usd": meta['cost_usd'],
                "sandbox_latency_ms": dur,
                "test_exit_code": rc,
            }
            self.telemetry["iterations_log"].append(iteration_record)
            self.telemetry["total_input_tokens"] += meta['input_tokens']
            self.telemetry["total_output_tokens"] += meta['output_tokens']
            self.telemetry["total_cost_usd"] += meta['cost_usd']

            if rc == 0:
                print(f"\n[VERIFIED] ALL TESTS PASSED GREEN AFTER {turn} ITERATION(S)!")
                self.telemetry["total_iterations"] = turn
                return True
            else:
                print(f"[DISCOVERY] New failure revealed in test suite. Advancing to next remediation cycle...")

        print(f"\n[EXHAUSTED] Reached maximum turns ({max_turns}) without complete resolution.")
        return False

def main():
    parser = argparse.ArgumentParser(description="PatchPilot Multi-Iteration Benchmark Agent")
    parser.add_argument("--backend", choices=["contree", "local"], default="contree", help="Sandbox execution backend")
    args = parser.parse_args()

    agent = BenchmarkAgent(backend=args.backend)
    success = agent.run_remediation(max_turns=5)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
