"""Measure query latency and error rate under concurrent load.

Example:
    python scripts/load_test.py \
      --url http://127.0.0.1:8000/api/v1/organizations/1/query \
      --token "$NEXORA_ACCESS_TOKEN" \
      --question "What is the leave policy?" \
      --requests 50 \
      --concurrency 10

The script intentionally uses only the Python standard library so it does not
change the production dependency set. It is a measurement tool, not a traffic
generator suitable for public targets.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = (len(values) - 1) * p
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    fraction = index - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def run_request(url: str, token: str, question: str, timeout: float) -> tuple[bool, float, int | None, str | None]:
    body = json.dumps({"question": question}).encode("utf-8")
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            response.read()
            status = response.status
        return 200 <= status < 300, (time.perf_counter() - started) * 1000, status, None
    except HTTPError as exc:
        return False, (time.perf_counter() - started) * 1000, exc.code, str(exc)
    except (URLError, TimeoutError, OSError) as exc:
        return False, (time.perf_counter() - started) * 1000, None, str(exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a bounded concurrent NEXORA query load test.")
    parser.add_argument("--url", required=True, help="NEXORA query endpoint")
    parser.add_argument("--token", required=True, help="Bearer access token")
    parser.add_argument("--question", required=True, help="Question sent to every request")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    if args.requests < 1 or args.concurrency < 1:
        parser.error("--requests and --concurrency must be positive")

    concurrency = min(args.concurrency, args.requests)
    latencies: list[float] = []
    failures: list[dict[str, object]] = []
    started = time.perf_counter()

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(run_request, args.url, args.token, args.question, args.timeout)
            for _ in range(args.requests)
        ]
        for future in as_completed(futures):
            ok, latency_ms, status, error = future.result()
            latencies.append(latency_ms)
            if not ok:
                failures.append({"status": status, "error": error})

    wall_ms = (time.perf_counter() - started) * 1000
    successful = len(latencies) - len(failures)
    wall_seconds = wall_ms / 1000

    print(f"requests={args.requests}")
    print(f"concurrency={concurrency}")
    print(f"successful={successful}")
    print(f"failed={len(failures)}")
    print(f"error_rate={len(failures) / args.requests:.4f}")
    print(f"throughput_rps={args.requests / wall_seconds:.3f}")
    print(f"latency_mean_ms={statistics.mean(latencies):.2f}")
    print(f"latency_median_ms={statistics.median(latencies):.2f}")
    print(f"latency_p95_ms={percentile(latencies, 0.95):.2f}")
    print(f"latency_p99_ms={percentile(latencies, 0.99):.2f}")
    print(f"latency_max_ms={max(latencies):.2f}")

    if failures:
        print("failures:")
        for failure in failures[:10]:
            print(json.dumps(failure, sort_keys=True))


if __name__ == "__main__":
    main()
