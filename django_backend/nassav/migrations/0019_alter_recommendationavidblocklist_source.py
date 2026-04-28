# Generated manually to align recommendation blocklist defaults with feedback semantics.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("nassav", "0018_recommendationavidblocklist_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="recommendationavidblocklist",
            name="source",
            field=models.CharField(db_index=True, default="manual", max_length=32),
        ),
    ]
