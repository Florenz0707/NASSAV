"""
Django settings for django_project project.
"""

import os
import re
import warnings
from pathlib import Path

from celery.schedules import crontab

from django_project.config_contract import (
    boolean,
    integer,
    load_env,
    load_yaml,
    url,
    validate_yaml,
)

# 过滤 StreamingHttpResponse 的 ASGI 警告
warnings.filterwarnings(
    "ignore",
    message=".*StreamingHttpResponse.*synchronous iterators.*",
    category=Warning,
)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load config from config.yaml
CONFIG_PATH = Path(
    os.getenv("NASSAV_CONFIG_PATH", str(BASE_DIR / "config" / "config.yaml"))
)
CONFIG = load_yaml(CONFIG_PATH)
validate_yaml(CONFIG, CONFIG_PATH)

# Process environment wins over development .env; YAML supplies remaining defaults.
ENV_PATH = Path(os.getenv("NASSAV_ENV_PATH", str(BASE_DIR / ".env")))
load_env(ENV_PATH)

# SECURITY WARNING: keep the secret key used in production secret!
# Load from environment first, fallback to insecure default for development only
SECRET_KEY = os.getenv(
    "SECRET_KEY", "django-insecure-nassav-backend-secret-key-change-in-production"
)

# SECURITY WARNING: don't run with debug turned on in production!
# Accept common truthy values from env vars
DEBUG = boolean(os.getenv("DEBUG", "false"), "DEBUG")

# ALLOWED_HOSTS can be provided via env var, comma-separated. Default to localhost only.
allowed_hosts_env = os.getenv("ALLOWED_HOSTS")
if allowed_hosts_env:
    ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_env.split(",") if h.strip()]
else:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

NASSAV_OPERATOR_USERNAME = os.getenv("NASSAV_OPERATOR_USERNAME", "nassav").strip()
if not NASSAV_OPERATOR_USERNAME:
    raise RuntimeError("NASSAV_OPERATOR_USERNAME must not be empty")

# Set true behind an HTTPS reverse proxy; local HTTP development keeps it false.
SECURE_SESSION_COOKIES = boolean(
    os.getenv("NASSAV_SECURE_COOKIES", "false"), "NASSAV_SECURE_COOKIES"
)
SESSION_COOKIE_SECURE = SECURE_SESSION_COOKIES
CSRF_COOKIE_SECURE = SECURE_SESSION_COOKIES
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
DOWNLOAD_PROXY_URL = (
    os.getenv("DOWNLOAD_PROXY_URL", (CONFIG.get("Proxy") or {}).get("download_url"))
    or None
)
if DOWNLOAD_PROXY_URL:
    url(
        DOWNLOAD_PROXY_URL,
        "DOWNLOAD_PROXY_URL/Proxy.download_url",
        schemes=("http", "https", "socks5", "socks5h"),
    )
VIDEO_HOST_DIR = os.getenv("VIDEO_HOST_DIR")

# Redis Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

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

# Cache Configuration
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "nassav",
        "TIMEOUT": 3600,  # 默认缓存1小时
    }
}

# External source search cache (single-user NAS friendly defaults)
EXTERNAL_SOURCE_SEARCH_CACHE_ENABLED = True
EXTERNAL_SOURCE_SEARCH_CACHE_TTL_DEFAULT = 1800  # actor/genre/keyword page
EXTERNAL_SOURCE_SEARCH_CACHE_TTL_HOT = 300  # hot board
EXTERNAL_SOURCE_SEARCH_CACHE_TTL_LATEST = 300  # latest updates

# Database settings come from config.yaml; environment variables override them for Compose.
DATABASE_CONFIG = CONFIG.get("Database") or {}
DB_ENGINE = (
    str(os.getenv("DB_ENGINE", DATABASE_CONFIG.get("Engine", "sqlite"))).strip().lower()
)
from django_project.db_mode_guard import verify_compose_db_mode

verify_compose_db_mode(DB_ENGINE)

if DB_ENGINE == "sqlite":
    sqlite_database_path = (
        os.getenv("DATABASE_PATH")
        or DATABASE_CONFIG.get("Path")
        or BASE_DIR / "db.sqlite3"
    )
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(sqlite_database_path),
            # WAL mode and timeout apply only to SQLite.
            "OPTIONS": {
                "init_command": "PRAGMA journal_mode=WAL;",
                "timeout": 20,
            },
        }
    }
elif DB_ENGINE in {"postgres", "postgresql"}:
    database_name = os.getenv("DB_NAME", DATABASE_CONFIG.get("Name"))
    database_user = os.getenv("DB_USER", DATABASE_CONFIG.get("User"))
    database_host = os.getenv("DB_HOST", DATABASE_CONFIG.get("Host"))
    missing_database_settings = [
        name
        for name, value in (
            ("DB_NAME/Database.Name", database_name),
            ("DB_USER/Database.User", database_user),
            ("DB_HOST/Database.Host", database_host),
        )
        if not value
    ]

    database_password_file = os.getenv(
        "DB_PASSWORD_FILE", DATABASE_CONFIG.get("PasswordFile")
    )
    database_password = os.getenv("DB_PASSWORD")
    if database_password and database_password_file:
        raise RuntimeError(
            "DB_PASSWORD conflicts with DB_PASSWORD_FILE/Database.PasswordFile"
        )
    if database_password_file:
        password_path = Path(database_password_file).expanduser()
        if not password_path.is_absolute():
            password_path = BASE_DIR / password_path
        try:
            database_password = password_path.read_text().rstrip("\r\n")
        except OSError as exc:
            raise RuntimeError("Database.PasswordFile cannot be read") from exc
    elif not database_password:
        database_password = DATABASE_CONFIG.get("Password")
    if not database_password:
        missing_database_settings.append(
            "DB_PASSWORD, DB_PASSWORD_FILE, or Database.Password"
        )
    if missing_database_settings:
        raise RuntimeError(
            "PostgreSQL requires explicit settings: "
            + ", ".join(missing_database_settings)
        )

    database_schema = str(
        os.getenv("DB_SCHEMA") or DATABASE_CONFIG.get("Schema") or "public"
    ).strip()
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", database_schema):
        raise RuntimeError(
            "Database.Schema must be a lowercase PostgreSQL identifier "
            "(1-63 characters, letters/digits/underscores)"
        )

    database_port = integer(
        os.getenv("DB_PORT", DATABASE_CONFIG.get("Port", 5432)),
        "DB_PORT/Database.Port",
        1,
        65535,
    )
    connection_max_age = integer(
        os.getenv("DB_CONN_MAX_AGE", DATABASE_CONFIG.get("ConnectionMaxAge", 60)),
        "DB_CONN_MAX_AGE/Database.ConnectionMaxAge",
        0,
    )
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": database_name,
            "USER": database_user,
            "PASSWORD": database_password,
            "HOST": database_host,
            "PORT": str(database_port),
            "CONN_MAX_AGE": connection_max_age,
            "OPTIONS": {"options": f"-c search_path={database_schema}"},
        }
    }
else:
    raise RuntimeError("DB_ENGINE must be 'sqlite' or 'postgres'")

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
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "nassav.access.OperatorSessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["nassav.access.IsOperator"],
    # Use drf-spectacular's AutoSchema for OpenAPI generation
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "NASSAV Backend API",
    "DESCRIPTION": "NASSAV 后端 API OpenAPI 文档",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
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
# Start separate workers with -Q scrape -c 1, -Q download -c 1, and -Q default.
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "nassav.tasks.recommendation_job_task": {"queue": "scrape"},
    "nassav.tasks.download_video_task": {"queue": "download"},
    "nassav.tasks.mock_download_video_task": {"queue": "download"},
    "nassav.scrape_jobs.run_resource_job": {"queue": "scrape"},
}
# 禁用 Worker 的任务成功/失败日志
CELERY_WORKER_SEND_TASK_EVENTS = False
CELERY_TASK_SEND_SENT_EVENT = False

# Resource paths - 新的布局：
# - 封面: resource/cover/{AVID}.jpg
# - 视频:  resource/video/{AVID}.mp4
# - 头像: resource/avatar/{filename}.jpg
RESOURCE_DIR = Path(os.getenv("NASSAV_RESOURCE_DIR", str(BASE_DIR / "resource")))
RESOURCE_DIR.mkdir(parents=True, exist_ok=True)

# 新的子目录
COVER_DIR = RESOURCE_DIR / "cover"
VIDEO_DIR = RESOURCE_DIR / "video"
AVATAR_DIR = RESOURCE_DIR / "avatar"
RECOMMENDATION_COVER_DIR = RESOURCE_DIR / "recommendation_cover"
COVER_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
RECOMMENDATION_COVER_DIR.mkdir(parents=True, exist_ok=True)

# Log directory
LOG_DIR = BASE_DIR / "log"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# User settings path
USER_SETTINGS_PATH = BASE_DIR / "config" / "user_settings.ini"
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
PROXY_CONFIG = CONFIG["Proxy"]
PROXY_ENABLED = boolean(PROXY_CONFIG["Enable"], "Proxy.Enable")
PROXY_URL = PROXY_CONFIG.get("url", None)

# Browser page fetching: new configuration wins as a whole; the old block is a fallback.
from nassav.page_fetching.factory import normalize_config, validate_strategy

try:
    BROWSER_FETCH_CONFIG = normalize_config(CONFIG)
except (TypeError, ValueError) as exc:
    raise RuntimeError(f"BrowserFetch configuration in {CONFIG_PATH}: {exc}") from None

# Source configurations
SOURCE_CONFIG = CONFIG.get("Source", {})
for _source_name, _source_data in SOURCE_CONFIG.items():
    if isinstance(_source_data, dict) and "browser_fetch_strategy" in _source_data:
        try:
            validate_strategy(_source_data["browser_fetch_strategy"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Source.{_source_name} in {CONFIG_PATH}: {exc}"
            ) from None

# Scraper configurations (e.g., JavBus, Busdmm, Dmmsee)
SCRAPER_CONFIG = CONFIG.get("Scraper", {})

# Translator configurations (e.g., Ollama)
TRANSLATOR_CONFIG = CONFIG.get("Translator", {})
ACTIVE_TRANSLATOR = CONFIG.get("Translator", {}).get("active", None)


# Celery Beat schedule: daily consistency checks
# Completed external-search jobs can be reused independently of source page caches.
EXTERNAL_SEARCH_RESULT_TTL_SECONDS = integer(
    CONFIG.get("ExternalSearch", {}).get("ResultTTLSeconds", 300),
    "ExternalSearch.ResultTTLSeconds",
    0,
    86400,
)

# Optional provider-facts policy; shared by API and every worker.
_cache_config = CONFIG.get("ResourceCache", {})
RESOURCE_CACHE_POLICY = {
    key: integer(_cache_config.get(key, default), f"ResourceCache.{key}", 1, maximum)
    for key, default, maximum in (
        ("SourceTTLSeconds", 604800, 31536000),
        ("ScraperTTLSeconds", 2592000, 31536000),
        ("PlaybackTTLSeconds", 300, 3600),
        ("MetadataRetentionDays", 90, 3650),
        ("PlaybackGraceHours", 24, 720),
        ("CleanupBatchSize", 500, 5000),
    )
}

CELERY_BEAT_SCHEDULE = {
    "cleanup-provider-cache": {
        "task": "nassav.tasks.cleanup_provider_cache",
        "schedule": crontab(hour="*/6", minute=10),
    },
    "db-disk-consistency-daily": {
        "task": "nassav.tasks.check_videos_consistency",
        "schedule": crontab(hour=7, minute=0),
        "args": (True, None, "celery_beat/videos_consistency_report.json"),
    },
    "actor-avatars-consistency-daily": {
        "task": "nassav.tasks.check_actor_avatars_consistency",
        "schedule": crontab(hour=7, minute=5),
        "args": (True, "celery_beat/actor_avatars_consistency_report.json"),
    },
    "backup-avid-list-daily": {
        "task": "nassav.tasks.backup_avid_list",
        "schedule": crontab(hour=2, minute=0),  # 每天凌晨 2:00 备份
    },
    "backup-database-daily": {
        "task": "nassav.tasks.backup_database",
        "schedule": crontab(hour=1, minute=30),  # 每天凌晨 1:30 备份数据库
        "args": (30,),  # days=30
    },
    "sync-backups-daily": {
        "task": "nassav.tasks.sync_backups",
        "schedule": crontab(hour=4, minute=0),  # 每天凌晨 4:00 同步备份
        "args": (None, 30),  # target=None(使用默认), days=30
    },
    "check-resources-consistency-daily": {
        "task": "nassav.tasks.check_resources_consistency",
        "schedule": crontab(hour=3, minute=0),  # 每天凌晨 3:00 检查并修复
        "args": (
            True,
            "celery_beat/resources_consistency_report.json",
        ),
    },
    "cleanup-logs-daily": {
        "task": "nassav.tasks.cleanup_logs",
        "schedule": crontab(hour=3, minute=30),  # 每天凌晨 3:30 清理本地过期日志
        "args": (30,),  # days=30
    },
}
