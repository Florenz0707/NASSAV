from django.contrib import admin
from .models import AVInfo


@admin.register(AVInfo)
class AVInfoAdmin(admin.ModelAdmin):
    list_display = ['avid', 'title', 'source', 'created_at', 'updated_at']
    list_filter = ['source', 'created_at']
    search_fields = ['avid', 'title']
    ordering = ['-created_at']
