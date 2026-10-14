from .base import *  # noqa: F401, F403
import environ

env = environ.Env()

DEBUG = False

# --- Secret key validation ---------------------------------------------------
# Production MUST have a real secret key; refuse to start with the dev default.

_INSECURE_DEFAULTS = {'insecure-dev-key-change-me', ''}

if SECRET_KEY in _INSECURE_DEFAULTS:  # noqa: F405
    raise ValueError(
        'DJANGO_SECRET_KEY is not set or is using the insecure default. '
        'Set a strong, unique DJANGO_SECRET_KEY environment variable for production.'
    )

# --- Reverse Proxy & Security Headers ----------------------------------------

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = env.bool('DJANGO_SECURE_SSL_REDIRECT', default=True)
SESSION_COOKIE_SECURE = env.bool('DJANGO_SESSION_COOKIE_SECURE', default=True)
CSRF_COOKIE_SECURE = env.bool('DJANGO_CSRF_COOKIE_SECURE', default=True)
SECURE_HSTS_SECONDS = env.int('DJANGO_SECURE_HSTS_SECONDS', default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# --- Production Database (PostgreSQL) ----------------------------------------

if env('DATABASE_URL', default=None):
    DATABASES['default'] = env.db('DATABASE_URL')  # noqa: F405

# --- Distributed Cache / Channel Layer (Redis) --------------------------------

REDIS_URL = env('REDIS_URL', default=None)
if REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_URL],
            },
        },
    }
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
        }
    }

# --- Logging with Data Minimization -------------------------------------------

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'production': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'production',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': env('DJANGO_LOG_LEVEL', default='INFO'),
    },
}

# --- Static Storage -----------------------------------------------------------
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
