"""
Django settings for django_project project.
"""

import os
import warnings
from pathlib import Path

import yaml
from celery.schedules import crontab

# 过滤 StreamingHttpResponse 的 ASGI 警告
warnings.filterwarnings(
    "ignore",
    message=".*StreamingHttpResponse.*synchronous iterators.*",
    category=Warning,
)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load config from config.yaml
CONFIG_PATH = BASE_DIR / "config" / "config.yaml"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

# Load environment variables from .env if present (simple parser, no extra dependency)
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as ef:
            for line in ef:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    # don't override existing environment variables
                    os.environ.setdefault(k, v)
    except Exception:
        pass

# SECURITY WARNING: keep the secret key used in production secret!
# Load from environment first, fallback to insecure default for development only
SECRET_KEY = os.getenv(
    "SECRET_KEY", "django-insecure-nassav-backend-secret-key-change-in-production"
)

# SECURITY WARNING: don't run with debug turned on in production!
# Accept common truthy values from env vars
DEBUG = str(os.getenv("DEBUG", "False")).lower() in ("1", "true", "yes")

# ALLOWED_HOSTS can be provided via env var, comma-separated. Default to localhost only.
allowed_hosts_env = os.getenv("ALLOWED_HOSTS")
if allowed_hosts_env:
    ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_env.split(",") if h.strip()]
else:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Redis Configuration
REDIS_URL = "redis://localhost:6379/0"

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
    "nassav",
    "channels",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "django_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "django_project.wsgi.application"
ASGI_APPLICATION = "django_project.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    }
}

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# REST Framework settings
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    # Use drf-spectacular's AutoSchema for OpenAPI generation
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "UNAUTHENTICATED_USER": None,
}

# Celery Configuration
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Shanghai"
# 限制并发数为1，确保同一时间只有一个下载任务在执行
CELERY_WORKER_CONCURRENCY = 1
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
# 禁用 Worker 的任务成功/失败日志
CELERY_WORKER_SEND_TASK_EVENTS = False
CELERY_TASK_SEND_SENT_EVENT = False

# Resource paths - 新的布局：
# - 封面: resource/cover/{AVID}.jpg
# - 视频:  resource/video/{AVID}.mp4
# - 头像: resource/avatar/{filename}.jpg
RESOURCE_DIR = BASE_DIR / "resource"
RESOURCE_DIR.mkdir(parents=True, exist_ok=True)

# 新的子目录
COVER_DIR = RESOURCE_DIR / "cover"
VIDEO_DIR = RESOURCE_DIR / "video"
AVATAR_DIR = RESOURCE_DIR / "avatar"
COVER_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
AVATAR_DIR.mkdir(parents=True, exist_ok=True)

# Log directory
LOG_DIR = BASE_DIR / "log"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        # More details for debugging: file, line and function name
        "verbose": {
            "format": "[%(asctime)s] %(levelname)s %(name)s %(pathname)s:%(lineno)d %(funcName)s: %(message)s"
        },
        "standard": {"format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "loggers": {
        # Django core
        "django": {"handlers": ["console"], "level": "INFO"},
        "django.request": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.server": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # Celery and dependencies
        "celery": {"handlers": ["console"], "level": "INFO", "propagate": True},
        "celery.app.trace": {
            "handlers": [],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

# Proxy settings from config
PROXY_CONFIG = CONFIG.get("Proxy", {})
PROXY_ENABLED = PROXY_CONFIG.get("Enable", False)
PROXY_URL = PROXY_CONFIG.get("url", None)

# Source configurations
SOURCE_CONFIG = CONFIG.get("Source", {})

# Scraper configurations (e.g., JavBus, Busdmm, Dmmsee)
SCRAPER_CONFIG = CONFIG.get("Scraper", {})

# Translator configurations (e.g., Ollama)
TRANSLATOR_CONFIG = CONFIG.get("Translator", {})
ACTIVE_TRANSLATOR = CONFIG.get("Translator", {}).get("active", "ollama")

# Display title configuration (title | source_title | translated_title)
DISPLAY_TITLE = CONFIG.get("DisplayTitle", "source_title")

# Celery Beat schedule: daily consistency checks
CELERY_BEAT_SCHEDULE = {
    "db-disk-consistency-daily": {
        "task": "nassav.tasks.check_videos_consistency",
        "schedule": crontab(hour=7, minute=0),
        "args": (False, None, "beat_report/videos_consistency_report.json"),
    },
    "actor-avatars-consistency-daily": {
        "task": "nassav.tasks.check_actor_avatars_consistency",
        "schedule": crontab(hour=6, minute=0),
        "args": (True, "beat_report/actor_avatars_report.json"),
    },
}
