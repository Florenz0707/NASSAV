"""Use an isolated file database so SQLite write waits behave like deployment."""

import os
import subprocess
import sys


def test_concurrent_feedback_reads_are_serialized_before_counting():
    code = r"""
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'django_project.refactoring_test_settings'
import django
django.setup()
from django.core.management import call_command
call_command('migrate', verbosity=0)
from threading import Event, Thread
from django.db import connection, close_old_connections
from nassav.recommendation.jobs import history_generation
from nassav.recommendation.feedback import recommendation_feedback_repository
from nassav.recommendation.repository import recommendation_snapshot_repository
from nassav.recommendation.entities import RecommendationRequest, RecommendationSeed, RecommendationCandidate, RecommendationExecution, RecommendationRun
from nassav.models import RecommendationSeedProfile
history_generation()
seed = RecommendationSeed('actor', 'Alice', 1, 'test')
item = RecommendationCandidate('RACE-1', 'Race', '', '', matched_seeds=[seed])
snapshot = recommendation_snapshot_repository.save_execution(RecommendationExecution('jable_page_lookup', 'local_preference', RecommendationRequest(), RecommendationRun([seed], [item])))
first_read = Event()
second_started = Event()
second_read = Event()
release = Event()
errors = []

def worker(first):
    close_old_connections()
    def inspect(execute, sql, params, many, context):
        if sql.startswith('SELECT') and 'recommendation_feedback' in sql.lower():
            if first:
                first_read.set()
                if not release.wait(5):
                    raise AssertionError('first feedback was never released')
            else:
                second_read.set()
        return execute(sql, params, many, context)
    try:
        if not first:
            second_started.set()
        with connection.execute_wrapper(inspect):
            recommendation_feedback_repository.record_feedback(snapshot_id=snapshot.pk, avid='RACE-1', feedback='like')
    except Exception as error:
        errors.append(str(error))
    finally:
        close_old_connections()

first = Thread(target=worker, args=(True,))
second = Thread(target=worker, args=(False,))
first.start()
assert first_read.wait(5), ('first feedback did not reach its existing-value read', errors)
second.start()
assert second_started.wait(5)
# A second request cannot observe the old value while the first transaction owns it.
assert not second_read.wait(0.3), 'concurrent request read feedback before the first committed'
release.set()
first.join(5)
second.join(5)
assert not first.is_alive() and not second.is_alive()
assert not errors, errors
assert second_read.is_set()
profile = RecommendationSeedProfile.objects.get(seed_type='actor', normalized_value='alice')
assert profile.accepted_count == 1, profile.accepted_count
assert profile.disliked_count == 0
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
