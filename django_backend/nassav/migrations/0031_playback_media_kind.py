from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("nassav", "0030_playback_refresh")]
    operations = [
        migrations.AddField(
            model_name="playbacksession",
            name="media_kind",
            field=models.CharField(default="source", max_length=16),
        ),
    ]
