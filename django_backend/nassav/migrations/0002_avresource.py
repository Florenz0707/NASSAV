"""Create AVResource, Actor, Genre models

Generated manually to add persistence models for AV metadata.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = False

    dependencies = [
        ("nassav", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Actor",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=200, unique=True, db_index=True)),
            ],
            options={
                "db_table": "nassav_actor",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Genre",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100, unique=True, db_index=True)),
            ],
            options={
                "db_table": "nassav_genre",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="AVResource",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("avid", models.CharField(max_length=50, unique=True, db_index=True)),
                ("title", models.CharField(blank=True, max_length=512, db_index=True)),
                ("source", models.CharField(blank=True, max_length=128, db_index=True)),
                (
                    "release_date",
                    models.CharField(blank=True, max_length=64, db_index=True),
                ),
                (
                    "duration",
                    models.IntegerField(blank=True, help_text="时长（秒）", null=True),
                ),
                ("metadata", models.JSONField(blank=True, null=True)),
                ("m3u8", models.TextField(blank=True, null=True)),
                (
                    "cover_filename",
                    models.CharField(
                        blank=True,
                        help_text="相对于 resource/{avid}/ 的封面文件名",
                        max_length=255,
                        null=True,
                    ),
                ),
                (
                    "file_exists",
                    models.BooleanField(
                        default=False, db_index=True, help_text="是否存在 MP4 文件"
                    ),
                ),
                ("file_size", models.BigIntegerField(blank=True, null=True)),
                ("metadata_saved_at", models.DateTimeField(auto_now=True)),
                ("video_saved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField()),
            ],
            options={
                "db_table": "nassav_avresource",
                "ordering": ["-metadata_saved_at"],
            },
        ),
        migrations.AddIndex(
            model_name="avresource",
            index=models.Index(fields=["avid"], name="nassav_avre_avid_idx"),
        ),
        migrations.AddIndex(
            model_name="avresource",
            index=models.Index(fields=["title"], name="nassav_avre_title_idx"),
        ),
        migrations.AddIndex(
            model_name="avresource",
            index=models.Index(fields=["source"], name="nassav_avre_source_idx"),
        ),
        migrations.AddField(
            model_name="avresource",
            name="actors",
            field=models.ManyToManyField(
                blank=True, related_name="resources", to="nassav.actor"
            ),
        ),
        migrations.AddField(
            model_name="avresource",
            name="genres",
            field=models.ManyToManyField(
                blank=True, related_name="resources", to="nassav.genre"
            ),
        ),
    ]
