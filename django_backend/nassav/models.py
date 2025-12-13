from django.db import models


class AVInfo(models.Model):
    """AV资源信息模型"""
    avid = models.CharField(max_length=50, unique=True, verbose_name='AV编号')
    title = models.CharField(max_length=500, verbose_name='标题')
    source = models.CharField(max_length=100, verbose_name='来源')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'av_info'
        verbose_name = 'AV信息'
        verbose_name_plural = 'AV信息'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.avid} - {self.title[:50]}'
