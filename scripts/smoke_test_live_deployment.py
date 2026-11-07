"""Run a real upload -> processing -> query -> SSE deployment smoke test.

Required environment:
  NEXORA_EMAIL
  NEXORA_PASSWORD

Example:
  NEXORA_EMAIL=smoke@example.com NEXORA_PASSWORD='...' \
    .venv/bin/python scripts/smoke_test_live_deployment.py \
    --base-url http://127.0.0.1:18001 \
    --pdf benchmark-data/LORA.pdf
"""

import argparse
import os
import time
from pathlib import Path

import httpx


QUESTIONS = (
    "What is the title of the uploaded paper, who are its authors, "
    "and what problem does it address?",
    "What does the paper report about the rank-four setting in its experiments?",
    "What is the LoRA low-rank update equation, and what do its matrices represent?",
    "What does this paper say about the company's cryptocurrency investment policy?",
)


def _login(client: httpx.Client, email: str, password: str) -> str:
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": "NEXORA Deployment Smoke",
            "password": password,
        },
    )
    if registration.status_code not in (201, 409):
        registration.raise_for_status()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("Login response did not contain an access token")
    return token


def _wait_until_ready(
    client: httpx.Client,
    organization_id: int,
    document_id: int,
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = client.get(
            f"/api/v1/organizations/{organization_id}/documents/{document_id}",
            headers=headers,
        )
        response.raise_for_status()
        document = response.json()
        status = document["status"]
        print(f"Document {document_id}: {status}", flush=True)

        if status == "ready":
            return document
        if status == "failed":
            raise RuntimeError(
                "Document processing failed: "
                + str(document.get("failure_reason"))
            )
        time.sleep(5)

    raise TimeoutError(
        f"Document {document_id} did not become READY within "
        f"{timeout_seconds} seconds"
    )


def _print_query_result(
    client: httpx.Client,
    organization_id: int,
    question: str,
    index: int,
    headers: dict[str, str],
) -> None:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/query",
        json={"question": question},
        headers=headers,
    )
    response.raise_for_status()
    result = response.json()

    print(f"\n===== QUERY {index} =====")
    print("Question:", question)
    print("Answer:", result["answer"])
    print("Sources:")
    for source in result.get("sources", []):
        print(
            "  citation=[{}] document={} pages={}-{} score={:.4f}".format(
                source["citation_index"],
                source.get("document_name"),
                source.get("page_start"),
                source.get("page_end"),
                source["score"],
            )
        )
    print("Timing:", result.get("timing"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise a deployed NEXORA instance using a real PDF."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("NEXORA_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path("benchmark-data/LORA.pdf"),
    )
    parser.add_argument("--wait-seconds", type=int, default=900)
    args = parser.parse_args()

    email = os.getenv("NEXORA_EMAIL")
    password = os.getenv("NEXORA_PASSWORD")
    if not email or not password:
        parser.error("Set NEXORA_EMAIL and NEXORA_PASSWORD in the environment")
    if not args.pdf.is_file():
        parser.error(f"PDF not found: {args.pdf}")

    base_url = args.base_url.rstrip("/")
    timeout = httpx.Timeout(900.0, connect=20.0)
    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        live = client.get("/health/live")
        live.raise_for_status()
        ready = client.get("/health/ready")
        ready.raise_for_status()
        print("API readiness:", ready.json())

        token = _login(client, email, password)
        headers = {"Authorization": f"Bearer {token}"}

        organization = client.post(
            "/api/v1/organizations",
            json={"name": f"NEXORA deployment smoke {int(time.time())}"},
            headers=headers,
        )
        organization.raise_for_status()
        organization_id = organization.json()["id"]
        print("Created smoke organization:", organization_id)

        with args.pdf.open("rb") as source_file:
            upload = client.post(
                f"/api/v1/organizations/{organization_id}/documents/upload",
                headers=headers,
                files={
                    "file": (
                        args.pdf.name,
                        source_file,
                        "application/pdf",
                    )
                },
            )
        upload.raise_for_status()
        document_id = upload.json()["id"]
        print("Uploaded document:", document_id)

        document = _wait_until_ready(
            client,
            organization_id,
            document_id,
            headers,
            args.wait_seconds,
        )
        print(
            "Document READY:",
            {
                "page_count": document.get("page_count"),
                "word_count": document.get("word_count"),
                "character_count": document.get("character_count"),
                "version": document.get("version"),
            },
        )

        for index, question in enumerate(QUESTIONS, start=1):
            _print_query_result(
                client,
                organization_id,
                question,
                index,
                headers,
            )

        print("\n===== SSE STREAM SMOKE TEST =====")
        with client.stream(
            "POST",
            f"/api/v1/organizations/{organization_id}/query/stream",
            headers=headers,
            json={"question": QUESTIONS[0]},
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    print(line)

        print("\nDeployment smoke test completed. Inspect answers, sources,")
        print("page references, and refusal behavior before accepting the deployment.")


if __name__ == "__main__":
    main()
