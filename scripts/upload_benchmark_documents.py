import json
import os
import subprocess
from pathlib import Path


API_URL = "http://127.0.0.1:8000"
ORGANIZATION_ID = int(os.environ["NEXORA_BENCHMARK_ORG_ID"])
TOKEN = os.environ["NEXORA_ACCESS_TOKEN"]

BENCHMARK_DIR = Path("benchmark-data")

for path in sorted(BENCHMARK_DIR.glob("*.docx")):
    print("=" * 80)
    print("Uploading:", path.name)

    result = subprocess.run(
        [
            "curl.exe",
            "-s",
            "-X",
            "POST",
            f"{API_URL}/api/v1/organizations/{ORGANIZATION_ID}/documents/upload",
            "-H",
            f"Authorization: Bearer {TOKEN}",
            "-F",
            (
                f"file=@{path};"
                "type=application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr)

    response = json.loads(result.stdout)

    if "id" not in response:
        raise RuntimeError(
            f"Upload failed for {path.name}: {response}"
        )

    print("Document ID:", response["id"])
    print("Status:", response["status"])
    print("Name:", response["name"])
