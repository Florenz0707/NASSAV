import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_credential_expansion_is_reversible_and_does_not_import_plaintext():
    before = [("nassav", "0039_library_access_grants")]
    after = [("nassav", "0041_source_credential_key_policy")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(before)
        apps = executor.loader.project_state(before).apps
        apps.get_model("nassav", "SourceCookie").objects.create(
            source_name="Jable", cookie="private-preserved"
        )
        for _ in range(2):
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            apps = executor.loader.project_state(after).apps
            assert not apps.get_model("nassav", "SourceCredential").objects.exists()
            assert not apps.get_model(
                "nassav", "SourceSessionSnapshot"
            ).objects.exists()
            assert (
                apps.get_model("nassav", "SourceCookie").objects.get().cookie
                == "private-preserved"
            )
            assert not apps.get_model(
                "nassav", "SourceCredentialKeyPolicy"
            ).objects.exists()
            MigrationExecutor(connection).migrate(before)
    finally:
        MigrationExecutor(connection).migrate(latest)
