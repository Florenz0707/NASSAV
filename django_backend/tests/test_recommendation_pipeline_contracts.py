"""Pure recommendation execution, registered extension and batched ORM inventory."""

from copy import deepcopy
import os
import subprocess
import sys
import pytest
from nassav.recommendation.base import AbstractRecommender
from nassav.recommendation.contracts import (
    CandidateInventory,
    RecommendationContextStore,
    SeedProvider,
)
from nassav.recommendation.entities import (
    RecommendationRequest,
    RecommendationCandidate,
    RecommendationSeed,
)
from nassav.recommendation.factors import NoveltyFactor
from nassav.recommendation.seed_selection import PreferenceSeedSelector
from nassav.recommendation.workflow import RecommenderManager
from nassav.recommendation.strategies import RecommendationStrategy


class Inventory(CandidateInventory):
    def __init__(self):
        self.batches = []

    def existing(self, avids):
        self.batches.append(set(avids))
        return avids & {"EXISTING"}


class Algorithm(AbstractRecommender):
    def build_seeds(self, request):
        return [RecommendationSeed("actor", "Alice", 1.0, "test")]

    def recall_candidates(self, seeds, request):
        return [
            RecommendationCandidate(avid, avid, "", "")
            for avid in ("EXISTING", "BLOCKED", "NEW-A", "NEW-B")
        ]


class Context(RecommendationContextStore):
    def next_random_seed(self):
        return 42

    def prepare(self, request, recommender_id, strategy_id):
        request.blocked_avid_blocklist = {"BLOCKED"}
        return "fingerprint"

    def persist(self, execution):
        return 7


class Seeds(SeedProvider):
    def get_seeds(self, request):
        return []

    def get_additional_seeds(self, request, *, used_seeds, batch_size):
        return []


def test_pure_pipeline_is_repeatable_and_does_not_mutate_input():
    inventory = Inventory()
    algorithm = Algorithm(candidate_inventory=inventory, factors=[NoveltyFactor()])
    request = RecommendationRequest(random_seed=42, blocked_avid_blocklist={"BLOCKED"})
    original = deepcopy(request)
    first, second = algorithm.recommend(request), algorithm.recommend(request)
    assert first.to_dict() == second.to_dict()
    assert request == original
    assert {item.avid for item in first.items} == {"NEW-A", "NEW-B"}
    assert first.execution_request is not request
    assert (
        len(inventory.batches) == 4
    )  # two phases per run, independent of candidate count


def test_new_recommender_uses_registry_without_manager_changes():
    def strategy():
        return RecommendationStrategy("test", "Test", "", ["new"], Seeds)

    manager = RecommenderManager(
        Context(),
        {"new": lambda selected: Algorithm(candidate_inventory=Inventory())},
        metadata={"new": {"id": "new", "name": "New", "description": ""}},
        strategy_builders={"test": strategy},
    )
    execution = manager.recommend("new", "test", {"random_seed": 42})
    assert execution.snapshot_id == 7
    assert {item.avid for item in execution.run.items} == {"NEW-A", "NEW-B"}
    assert all(item.snapshot_id == 7 for item in execution.run.items)


def test_seed_selection_is_pure_and_keeps_input_history():
    seeds = [
        RecommendationSeed("actor", f"Actor {i}", 1, "test", resource_count=i)
        for i in range(9)
    ]
    request = RecommendationRequest(
        actor_preference="rare", recent_seed_counts={"actor:Actor 1": 3}
    )
    original = deepcopy(request)
    selector = PreferenceSeedSelector()
    first = selector.select(seeds=seeds, limit=3, request=request, seed_type="actor")
    assert first == selector.select(
        seeds=seeds, limit=3, request=request, seed_type="actor"
    )
    assert len(first) == 3 and request == original


@pytest.mark.django_db
def test_inventory_query_count_does_not_grow_with_candidates(
    resource_factory, django_assert_num_queries
):
    from nassav.recommendation.data_access import DjangoCandidateInventory

    resource_factory(avid="EXISTING")
    for count in (1, 100):
        with django_assert_num_queries(1):
            assert DjangoCandidateInventory().existing(
                {"EXISTING"} | {f"NEW-{i}" for i in range(count)}
            ) == {"EXISTING"}


def test_algorithm_imports_without_django_configuration():
    env = os.environ.copy()
    env.pop("DJANGO_SETTINGS_MODULE", None)
    code = "import sys; import nassav.recommendation.base, nassav.recommendation.jable_search, nassav.recommendation.seed_selection; assert 'django' not in sys.modules"
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr
