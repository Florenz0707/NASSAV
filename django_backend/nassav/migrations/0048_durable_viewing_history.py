"""History retains proven personal events, independently of physical resource lifetime."""

from django.db import migrations, models
import django.db.models.deletion


def backfill(apps, schema_editor):
    alias = schema_editor.connection.alias
    History = apps.get_model("nassav", "UserWatchHistory")
    Pool = apps.get_model("nassav", "ResourcePoolEntry")
    for history in (
        History.objects.using(alias).select_related("resource").iterator(chunk_size=200)
    ):
        resource = history.resource
        avid = resource.avid.strip().upper()
        pool, _ = Pool.objects.using(alias).get_or_create(
            canonical_avid=avid, defaults={"resource_id": resource.pk, "state": "ready"}
        )
        if pool.resource_id not in {None, resource.pk}:
            raise RuntimeError(
                "History resource identity conflicts; resolve before migration"
            )
        history.pool_id = pool.pk
        history.snapshot = {
            "avid": avid,
            "original_title": resource.original_title or "",
            "source_title": resource.source_title or "",
            "translated_title": resource.translated_title or "",
            "source": resource.source or "",
        }
        history.save(using=alias, update_fields=["pool", "snapshot"])
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def reverse_guard(apps, schema_editor):
    History = apps.get_model("nassav", "UserWatchHistory")
    if (
        History.objects.using(schema_editor.connection.alias)
        .filter(resource__isnull=True)
        .exists()
    ):
        raise RuntimeError(
            "History survives reclaimed resources; restore backup instead of discarding history"
        )
    if schema_editor.connection.vendor == "postgresql":
        # Backfill/reverse DDL shares one transaction; drain deferred FK triggers.
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


class Migration(migrations.Migration):
    dependencies = [("nassav", "0047_owned_catalog_projection")]
    operations = [
        migrations.AddField(
            model_name="userwatchhistory",
            name="pool",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="nassav.resourcepoolentry",
            ),
        ),
        migrations.AddField(
            model_name="userwatchhistory",
            name="snapshot",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="userwatchhistory",
            name="resource",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="nassav.avresource",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="userwatchhistory", name="nassav_user_history_unique"
        ),
        migrations.RunPython(backfill, reverse_guard),
        migrations.AlterField(
            model_name="userwatchhistory",
            name="pool",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="nassav.resourcepoolentry",
            ),
        ),
        migrations.AddConstraint(
            model_name="userwatchhistory",
            constraint=models.UniqueConstraint(
                fields=["user", "pool"], name="nassav_user_history_unique"
            ),
        ),
    ]
