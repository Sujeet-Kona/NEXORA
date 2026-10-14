"""Authenticated smoke test for a running NEXORA production stack.

The script intentionally exercises only control-plane endpoints so it can run
without an LLM provider. Document ingestion/query remains a deployment-host
acceptance test because it depends on the configured embedding and LLM runtime.
"""

import argparse
import json
import time
import urllib.error
import urllib.request
import uuid


def request_json(base_url: str, method: str, path: str, payload=None, token=None):
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=body,
        method=method,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    with urllib.request.urlopen(base_url + "/health", timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"health check returned HTTP {response.status}")

    suffix = uuid.uuid4().hex[:10]
    email = f"prod-smoke-{suffix}@example.com"
    password = "NexoraSmoke!2026"

    status, user = request_json(
        base_url,
        "POST",
        "/api/v1/auth/register",
        {
            "email": email,
            "full_name": "NEXORA Production Smoke",
            "password": password,
        },
    )
    assert status == 201 and user["email"] == email

    status, tokens = request_json(
        base_url,
        "POST",
        "/api/v1/auth/login",
        {"email": email, "password": password},
    )
    assert status == 200 and tokens["access_token"]
    access_token = tokens["access_token"]

    status, me = request_json(
        base_url,
        "GET",
        "/api/v1/auth/me",
        token=access_token,
    )
    assert status == 200 and me["email"] == email

    status, organization = request_json(
        base_url,
        "POST",
        "/api/v1/organizations",
        {"name": f"Smoke Organization {suffix}"},
        token=access_token,
    )
    assert status == 201 and organization["name"].startswith("Smoke Organization")

    print("Production control-plane smoke test: PASS")
    print("  health: PASS")
    print("  register: PASS")
    print("  login: PASS")
    print("  authenticated /me: PASS")
    print("  create organization: PASS")
    print(f"  organization_id: {organization['id']}")


if __name__ == "__main__":
    main()
