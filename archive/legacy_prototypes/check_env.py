import os

env_file = os.path.join(os.path.dirname(__file__), ".env")
exists = os.path.exists(env_file)
print("File exists:", exists)
if exists:
    size = os.path.getsize(env_file)
    print(f"File size: {size} bytes")
    with open(env_file, "r", encoding="utf-8") as f:
        keys_found = []
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("\"'")
                if v and not v.startswith("your_"):
                    keys_found.append((k, len(v)))
    print("Populated keys (names and lengths only):", keys_found)
