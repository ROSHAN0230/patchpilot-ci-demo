"""
PatchPilot Hard Gate 1: Real Credential & Platform Verification Script.
Safely tests external authentication, model availability, sandbox execution, and Tavily without exposing secrets.
"""

import os
import sys
import time
import requests
from dotenv import load_dotenv

# Load local .env if present
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

def print_header(title: str):
    print("\n" + "=" * 65)
    print(f" {title}")
    print("=" * 65)

def mask_key(k: str) -> str:
    if not k:
        return "[NOT SET]"
    if len(k) <= 8:
        return "[SET - ***]"
    return f"[SET - {k[:4]}...{k[-4:]}]"

def test_nebius_inference():
    print_header("GATE 1.1: NEBIUS TOKEN FACTORY & NEMOTRON MODEL")
    api_key = os.environ.get("NEBIUS_API_KEY", "").strip()

    if not api_key:
        print("[FAIL] NEBIUS_API_KEY is not set.")
        print("       Action: Set it in C:\\Users\\raahe\\.gemini\\antigravity\\scratch\\patchpilot-poc\\.env")
        print("               or run $env:NEBIUS_API_KEY='your-key' in PowerShell.")
        return False, None

    print(f"[*] API Key present: {mask_key(api_key)}")
    base_url = "https://api.tokenfactory.nebius.com/v1"
    headers = {"Authorization": f"Bearer {api_key}"}

    # Step 1: Query /models
    print(f"[*] Calling GET {base_url}/models...")
    try:
        t0 = time.time()
        resp = requests.get(f"{base_url}/models", headers=headers, timeout=12)
        latency = (time.time() - t0) * 1000

        if resp.status_code != 200:
            print(f"[FAIL] /models returned HTTP {resp.status_code}: {resp.text}")
            return False, None

        data = resp.json()
        all_models = [m.get("id") for m in data.get("data", [])]
        print(f"[PASS] Authentication successful. HTTP 200 in {latency:.1f}ms.")
        print(f"       Total models accessible: {len(all_models)}")

        # Step 2: Check target Nemotron model
        target_candidates = [
            "nvidia/nemotron-3-super-120b-a12b",
            "nebius/nvidia/nemotron-3-super-120b-a12b",
            "nvidia/nemotron-3-ultra-550b",
            "nebius/nvidia/Nemotron-3-Ultra-550b-a55b",
            "nvidia/nemotron-3-nano-30b",
            "nebius/nvidia/nemotron-3-nano-30b",
        ]

        verified_model = None
        for candidate in target_candidates:
            if candidate in all_models:
                verified_model = candidate
                break

        if not verified_model:
            # Search for any nemotron model ID
            matches = [m for m in all_models if "nemotron" in m.lower()]
            if matches:
                verified_model = matches[0]

        if not verified_model:
            print("[FAIL] No NVIDIA Nemotron model found in active catalog.")
            print(f"       Available models sample: {all_models[:6]}")
            return False, None

        print(f"[PASS] Target Nemotron model found: '{verified_model}'")

        # Step 3: 1-token live inference smoke test
        print(f"[*] Testing live completion on '{verified_model}'...")
        t0 = time.time()
        chat_resp = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={
                "model": verified_model,
                "messages": [{"role": "user", "content": "Return the single word: PONG"}],
                "max_tokens": 100,
                "temperature": 0.0,
            },
            timeout=30,
        )
        chat_latency = (time.time() - t0) * 1000

        if chat_resp.status_code == 200:
            msg_obj = chat_resp.json()["choices"][0]["message"]
            content = (msg_obj.get("content") or msg_obj.get("reasoning") or "").strip()
            print(f"[PASS] Inference verified! Output: '{content}' ({chat_latency:.1f}ms)")
            return True, verified_model
        else:
            print(f"[FAIL] Inference failed (HTTP {chat_resp.status_code}): {chat_resp.text}")
            return False, verified_model

    except Exception as e:
        print(f"[FAIL] Network / connection error: {e}")
        return False, None

def test_contree_sandbox():
    print_header("GATE 1.2: TOKEN FACTORY SANDBOXES (CONTREE)")
    api_key = os.environ.get("NEBIUS_API_KEY", "").strip()
    project_id = os.environ.get("NEBIUS_PROJECT_ID", "").strip()

    if not api_key:
        print("[FAIL] NEBIUS_API_KEY not set. Cannot test ConTree Sandboxes.")
        return False

    print(f"[*] ConTree Endpoint: https://api.tokenfactory.nebius.com/sandboxes/")
    print(f"[*] NEBIUS_PROJECT_ID: {project_id if project_id else '[NOT SET]'}")

    try:
        from contree_sdk import ContreeSync
        from contree_sdk.config import ContreeConfig
        from contree_sdk.auth import IAMAuth

        auth = IAMAuth(token=api_key, project_id=project_id)
        config = ContreeConfig(auth=auth)
        client = ContreeSync(config=config)

        print("[*] Probing sandbox authentication & token info...")
        t0 = time.time()
        try:
            token_info = client.get_token_info()
            print(f"[PASS] ConTree API authenticated! ({time.time() - t0:.2f}s)")
            print(f"       Token info status: {token_info}")

            # Step 2: Try executing a harmless command in a minimal container
            print("[*] Spawning test sandbox with image 'python:3.11-slim'...")
            t_exec = time.time()
            image = client.images.use("python:3.11-slim")
            op = image.run(shell='python -c "print(\'CONTREE_ONLINE\')"')
            result = op.wait()
            exec_time = time.time() - t_exec

            output = result.stdout.strip()
            if "CONTREE_ONLINE" in output:
                print(f"[PASS] Harmless sandbox command executed successfully! ({exec_time:.2f}s)")
                print(f"       Stdout: '{output}'")
                return True
            else:
                print(f"[FAIL] Command completed but unexpected stdout: '{output}'")
                return False

        except Exception as e:
            err_str = str(e)
            print(f"[NOTE] ConTree probe returned: {err_str}")
            if "403" in err_str or "unauthorized" in err_str.lower() or "forbidden" in err_str.lower():
                print("       -> Diagnosis: Account lacks beta sandbox permissions or NEBIUS_PROJECT_ID.")
            elif "404" in err_str:
                print("       -> Diagnosis: Sandbox endpoint not found / path unprovisioned.")
            return False

    except ImportError:
        print("[FAIL] contree-sdk not installed in environment.")
        return False
    except Exception as e:
        print(f"[FAIL] Unexpected ConTree error: {e}")
        return False

def test_tavily():
    print_header("GATE 1.3: TAVILY API ($3,000 BONUS PREREQUISITE)")
    tavily_key = os.environ.get("TAVILY_API_KEY", "").strip()

    if not tavily_key:
        print("[FAIL] TAVILY_API_KEY is not set.")
        print("       Action: Set TAVILY_API_KEY in .env or via PowerShell.")
        return False

    print(f"[*] Tavily Key present: {mask_key(tavily_key)}")
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=tavily_key)
        print("[*] Executing test query: 'Pydantic V2 migration guide'...")
        t0 = time.time()
        res = client.search(query="Pydantic V2 migration guide field_validator", max_results=1)
        latency = (time.time() - t0) * 1000

        results = res.get("results", [])
        if results:
            print(f"[PASS] Tavily verified! Retrieved 1 result in {latency:.1f}ms.")
            print(f"       URL: {results[0].get('url')}")
            return True
        else:
            print("[FAIL] Tavily returned 0 results.")
            return False
    except Exception as e:
        print(f"[FAIL] Tavily API call failed: {e}")
        return False

def main():
    print("\n" + "#" * 65)
    print("  PATCHPILOT: HARD GATE 1 - REAL PLATFORM CREDENTIAL VERIFICATION")
    print("#" * 65)

    inf_ok, model_id = test_nebius_inference()
    sandbox_ok = test_contree_sandbox()
    tavily_ok = test_tavily()

    print_header("HARD GATE 1 FINAL VERDICT")
    print(f"1. Nebius Inference:  {'PASSED' if inf_ok else 'FAILED'}")
    print(f"2. ConTree Sandbox:   {'PASSED' if sandbox_ok else 'FAILED'}")
    print(f"3. Tavily Search:     {'PASSED' if tavily_ok else 'FAILED'}")

    all_passed = inf_ok and tavily_ok  # ConTree is optional for local fallback, but required for Gate 1 sandbox
    if inf_ok and tavily_ok and sandbox_ok:
        print("\n--> ALL EXTERNAL GATES PASSED! Ready for Hard Gate 2.")
        sys.exit(0)
    elif inf_ok and tavily_ok:
        print("\n--> Inference & Tavily PASSED. Sandbox access requires ConTree approval or local fallback.")
        sys.exit(2)
    else:
        print("\n--> CRITICAL GATE FAILED. Cannot proceed to Hard Gate 2 until credentials are provided.")
        sys.exit(1)

if __name__ == "__main__":
    main()
