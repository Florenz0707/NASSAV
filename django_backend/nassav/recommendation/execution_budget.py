"""Recommendation network admission, independent of transport and persistence."""

import time

from nassav.task_network import TaskNetworkTimeout


class RecommendationBudgetExhausted(TaskNetworkTimeout):
    """Network work stopped early so validated results can be finalized."""


class RecommendationExecutionBudget:
    def __init__(self, seconds, *, report=None, clock=time.monotonic, reserve=30):
        self.clock = clock
        self.started = clock()
        self.deadline = self.started + max(0, seconds - reserve)
        self.report = report or (lambda progress: None)
        self.exhausted = False
        self.stage = "recall"

    def check(self):
        if self.exhausted or self.clock() >= self.deadline:
            self.exhausted = True
            raise RecommendationBudgetExhausted("推荐网络预算已用尽，准备收尾")

    def publish(self, stage, *, candidates=0, verified=0, attempted=0, statistics=None):
        self.stage = stage
        self.report(
            {
                **(statistics or {}),
                "stage": stage,
                "candidate_count": candidates,
                "verified_count": verified,
                "detail_attempt_count": attempted,
                "elapsed_seconds": round(self.clock() - self.started, 1),
                "network_remaining_seconds": round(
                    max(0, self.deadline - self.clock()), 1
                ),
            }
        )
