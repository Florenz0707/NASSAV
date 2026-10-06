"""Gate tests: failures, missing windows, repeated pages and false positives."""

from copy import deepcopy

import pytest
from scripts.assess_byparr_acceptance import assess


def evidence():
    cold, warm = [], []
    for window in ("W1", "W2"):
        warm.append(dict(stage="seed_probe", window=window, valid=True))
        for index in range(20):
            for candidate in (False, True):
                cold.append(
                    dict(
                        stage="detail",
                        window=window,
                        candidate=candidate,
                        sample=f"TEST-{index}",
                        valid=True,
                        client_ms=20000,
                    )
                )
            warm.append(
                dict(
                    stage="warm",
                    window=window,
                    sample=f"TEST-{index}",
                    valid_page=True,
                    direct_valid=True,
                    browser_calls=0,
                    total_ms=1000,
                )
            )
        for candidate in (False, True):
            cold.append(
                dict(stage="negative", window=window, candidate=candidate, valid=False)
            )
    return cold, warm


def test_both_windows_must_meet_every_gate():
    cold, warm = evidence()
    result = assess(cold, warm)
    assert result["decision"] == "PRE_SCREEN_PASS"
    assert result["runtime_checks_eligible"]
    assert not result["observation_24h_eligible"]
    assert assess(cold, warm[:21])["decision"] == "NO_GO"


@pytest.mark.parametrize(
    "change",
    [
        "slow_failure",
        "direct_failures",
        "refreshes",
        "false_positive",
        "duplicate_pages",
    ],
)
def test_bad_evidence_cannot_be_hidden_by_valid_sample_filter(change):
    cold, warm = deepcopy(evidence())
    details = [r for r in warm if r["stage"] == "warm"]
    if change == "slow_failure":
        for row in details[:2]:
            row.update(valid_page=False, total_ms=60000)
    elif change == "direct_failures":
        for row in details[:2]:
            row["direct_valid"] = False
    elif change == "refreshes":
        for row in details[:2]:
            row["browser_calls"] = 1
    elif change == "false_positive":
        cold[-1]["valid"] = True
    else:
        for row in cold:
            row["sample"] = "SAME-001"
    result = assess(cold, warm)
    assert result["decision"] == "NO_GO"
    assert not result["runtime_checks_eligible"]
    if change == "slow_failure":
        assert result["windows"][0]["warm_p95_ms"] == 60000


def test_failed_cookie_api_blocks_observation_despite_passing_prescreen():
    cold, warm = evidence()
    result = assess(cold, warm, [{"stage": "cookie_api", "automatic_status": 500}])
    assert result["runtime_checks_eligible"]
    assert result["decision"] == "NO_GO"
    assert not result["observation_24h_eligible"]


def test_observation_requires_all_runtime_gates_and_keeps_earlier_failures():
    cold, warm = evidence()
    runtime = [
        {"stage": "cookie_api", "automatic_status": 200},
        {"stage": "cookie_pairing", "paired": True},
        {
            "stage": "runtime_summary",
            "phase": "serial",
            "valid": True,
            "tasks": 1,
            "terminal_websocket_events": 1,
        },
        {
            "stage": "runtime_summary",
            "phase": "mixed",
            "valid": True,
            "tasks": 10,
            "browser_calls": 0,
        },
        {"stage": "sync_api", "status": 200},
        {"stage": "media_download", "valid": True},
        {"stage": "rollback", "valid": True},
    ]
    assert assess(cold, warm, runtime)["decision"] == "READY_FOR_OBSERVATION"
    runtime.insert(0, {"stage": "cookie_api", "automatic_status": 500})
    assert assess(cold, warm, runtime)["decision"] == "NO_GO"
