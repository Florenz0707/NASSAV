"""Assess P5 gates from sanitized cold A/B and warm-session JSONL evidence.

Usage: uv run python scripts/assess_byparr_acceptance.py --cold FILE FILE
  --warm FILE FILE
No network calls or configuration writes. Exit 2 means NO-GO, not probe failure.
"""

import argparse
import json
from math import ceil
from statistics import median


def p95(values):
    return sorted(values)[ceil(len(values) * 0.95) - 1] if values else None


def assess(cold, warm, runtime=None):
    cold = [r for r in cold if r.get("source", "Jable") == "Jable"]
    windows = []
    for window in ("W1", "W2"):
        baseline = [
            r
            for r in cold
            if r.get("stage") == "detail"
            and r.get("window") == window
            and not r.get("candidate")
        ]
        candidate = [
            r
            for r in cold
            if r.get("stage") == "detail"
            and r.get("window") == window
            and r.get("candidate")
        ]
        negatives = [
            r
            for r in cold
            if r.get("stage") == "negative" and r.get("window") == window
        ]
        requests = [
            r for r in warm if r.get("stage") == "warm" and r.get("window") == window
        ]
        baseline_ms = median([r["client_ms"] for r in baseline]) if baseline else None
        warm_ms = p95([r["total_ms"] for r in requests])
        rate = (
            sum(bool(r["direct_valid"]) for r in requests) / len(requests)
            if requests
            else 0
        )
        first_ten_calls = sum(r["browser_calls"] for r in requests[:10])
        checks = {
            "baseline_valid_20": len({r["sample"] for r in baseline if r["valid"]})
            >= 20,
            "candidate_valid_20": len({r["sample"] for r in candidate if r["valid"]})
            >= 20,
            "warm_valid_20": len({r["sample"] for r in requests if r["valid_page"]})
            >= 20,
            "verified_seed": any(
                r.get("stage") == "seed_probe"
                and r.get("window") == window
                and r.get("valid")
                for r in warm
            ),
            "direct_success_95_percent": rate >= 0.95,
            "negative_zero_false_positive": {r.get("candidate") for r in negatives}
            == {False, True}
            and not any(r["valid"] for r in negatives),
            "warm_p95_under_5s": warm_ms is not None and warm_ms < 5000,
            "warm_p95_under_baseline_quarter": warm_ms is not None
            and baseline_ms is not None
            and warm_ms < baseline_ms * 0.25,
            "first_ten_at_most_one_browser_call": len(requests) >= 10
            and first_ten_calls <= 1,
        }
        windows.append(
            {
                "window": window,
                "checks": checks,
                "direct_rate": rate,
                "warm_p95_ms": warm_ms,
                "baseline_median_ms": baseline_ms,
                "first_ten_browser_calls": first_ten_calls,
            }
        )
    passed = all(all(w["checks"].values()) for w in windows)
    runtime_checks = {
        "cookie_auto_and_pairing": bool(runtime)
        and any(
            r.get("stage") == "cookie_api" and r.get("automatic_status") == 200
            for r in runtime
        )
        and any(
            r.get("stage") == "cookie_pairing" and r.get("paired") for r in runtime
        ),
        "cookie_no_failed_attempt": bool(runtime)
        and not any(
            r.get("stage") == "cookie_api" and r.get("automatic_status") != 200
            for r in runtime
        ),
        "serial_tasks_and_websocket": bool(runtime)
        and any(
            r.get("stage") == "runtime_summary"
            and r.get("phase") == "serial"
            and r.get("tasks", 0) >= 1
            and r.get("terminal_websocket_events", 0) >= r.get("tasks", 1)
            for r in runtime
        ),
        "mixed_tasks_and_websocket": bool(runtime)
        and any(
            r.get("stage") == "runtime_summary"
            and r.get("phase") == "mixed"
            and r.get("valid")
            and r.get("tasks", 0) >= 10
            and r.get("browser_calls", 99) <= 1
            for r in runtime
        ),
        "sync_api": bool(runtime)
        and any(
            r.get("stage") == "sync_api" and r.get("status") == 200 for r in runtime
        ),
        "media_download": bool(runtime)
        and any(r.get("stage") == "media_download" and r.get("valid") for r in runtime),
        "rollback": bool(runtime)
        and any(r.get("stage") == "rollback" and r.get("valid") for r in runtime),
        "no_runtime_failures": bool(runtime)
        and not any(r.get("stage") == "runtime_failure" for r in runtime),
    }
    eligible = passed and all(runtime_checks.values())
    decision = (
        "PRE_SCREEN_PASS"
        if passed and runtime is None
        else "READY_FOR_OBSERVATION"
        if eligible
        else "NO_GO"
    )
    return {
        "decision": decision,
        "windows": windows,
        "runtime_checks_eligible": passed,
        "observation_24h_eligible": eligible,
        "runtime_checks": runtime_checks,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cold", nargs="+", required=True)
    parser.add_argument("--warm", nargs="+", required=True)
    parser.add_argument(
        "--runtime", nargs="+", help="Optional API/worker/rollback/media JSONL"
    )
    args = parser.parse_args()

    def read(paths):
        rows = []
        for path in paths:
            with open(path) as stream:
                rows.extend(json.loads(line) for line in stream if line.strip())
        return rows

    result = assess(
        read(args.cold), read(args.warm), read(args.runtime) if args.runtime else None
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 2 if result["decision"] == "NO_GO" else 0


if __name__ == "__main__":
    raise SystemExit(main())
