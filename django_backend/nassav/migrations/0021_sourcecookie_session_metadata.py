from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("nassav", "0020_increase_translated_title_length")]

    operations = [
        migrations.AddField(
            model_name="sourcecookie",
            name="user_agent",
            field=models.TextField(
                blank=True, null=True, verbose_name="配套 User-Agent"
            ),
        ),
        migrations.AddField(
            model_name="sourcecookie",
            name="expires_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="会话到期时间"
            ),
        ),
        migrations.AddField(
            model_name="sourcecookie",
            name="egress_profile",
            field=models.CharField(
                blank=True, max_length=64, null=True, verbose_name="代理路由标识"
            ),
        ),
    ]
