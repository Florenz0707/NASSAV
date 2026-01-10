"""
Celery configuration for django_project.
"""
import os

from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")

app = Celery("django_project")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object("django.conf:settings", namespace="CELERY")

# 禁用 Celery Worker 的任务成功日志
app.conf.worker_log_format = "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s"
app.conf.worker_task_log_format = "[%(asctime)s: %(levelname)s/%(processName)s] %(task_name)s[%(task_id)s]: %(message)s"
app.conf.task_track_started = False
app.conf.worker_redirect_stdouts = False

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
