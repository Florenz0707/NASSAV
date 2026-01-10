# Generated manually on 2026-01-10

from django.db import migrations, models
from django.utils import timezone


def copy_metadata_updated_at_to_created_at(apps, schema_editor):
    """将现有的 metadata_updated_at 复制到 metadata_created_at"""
    AVResource = apps.get_model("nassav", "AVResource")
    # 使用 update 而不是 save 来避免触发 auto_now
    db_alias = schema_editor.connection.alias
    for resource in AVResource.objects.using(db_alias).all():
        AVResource.objects.using(db_alias).filter(pk=resource.pk).update(
            metadata_created_at=resource.metadata_updated_at
        )


class Migration(migrations.Migration):
    dependencies = [
        ("nassav", "0010_remove_avresource_nassav_avre_title_d0556f_idx_and_more"),
    ]

    operations = [
        # 第一步：更新模型的 Meta 选项（先改为临时排序）
        migrations.AlterModelOptions(
            name="avresource",
            options={"ordering": ["-created_at"]},
        ),
        # 第二步：重命名 metadata_saved_at 为 metadata_updated_at
        migrations.RenameField(
            model_name="avresource",
            old_name="metadata_saved_at",
            new_name="metadata_updated_at",
        ),
        # 第三步：添加 metadata_created_at 字段
        migrations.AddField(
            model_name="avresource",
            name="metadata_created_at",
            field=models.DateTimeField(blank=True, null=True, help_text="元数据首次创建时间"),
        ),
        # 第四步：将 metadata_updated_at 的值复制到 metadata_created_at
        migrations.RunPython(
            copy_metadata_updated_at_to_created_at,
            reverse_code=migrations.RunPython.noop,
        ),
        # 第五步：更新模型的 Meta 选项（改为正确的排序）
        migrations.AlterModelOptions(
            name="avresource",
            options={"ordering": ["-metadata_updated_at"]},
        ),
    ]
