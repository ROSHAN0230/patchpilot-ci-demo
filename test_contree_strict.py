import os
from dotenv import load_dotenv
from contree_sdk import ContreeSync
from contree_sdk.config import ContreeConfig
from contree_sdk.auth import IAMAuth

load_dotenv()
api_key = os.environ.get("NEBIUS_API_KEY", "").strip()
project_id = os.environ.get("NEBIUS_PROJECT_ID", "").strip()

print(f"[*] API Key Present: {bool(api_key)}")
print(f"[*] Project ID      : {project_id}")

auth = IAMAuth(token=api_key, project_id=project_id)
config = ContreeConfig(auth=auth)
client = ContreeSync(config=config)

print("[*] Probing whoami...")
info = client.get_token_info()
print("Token UUID  :", info.token_uuid)
print("Permissions :", info.permissions)
print("Limits      :", info.limits)

print("\n[*] Attempting image run with python:3.11-slim...")
try:
    img = client.images.use("python:3.11-slim")
    op = img.run(shell="echo CONTREE_ONLINE")
    res = op.wait()
    print("[PASS] Execution Output:", res.stdout.strip())
except Exception as e:
    print(f"[FAIL] Exact Error: {type(e).__name__}: {e}")
