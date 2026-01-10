"""
URL configuration for django_project project.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("nassav/", include("nassav.urls")),
]
