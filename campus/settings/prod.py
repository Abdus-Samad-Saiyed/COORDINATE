import sys
import environ

from .base import *  # noqa: F401, F403


class ImproperlyConfigured(ValueError):
    """Configuration error for production environment."""
    pass


env = environ.Env()

DEBUG = False

# Production MUST never import secrets_local
if 'secrets_local' in globals() or 'campus.settings.secrets_local' in sys.modules:
    raise ImproperlyConfigured("Production settings must not import secrets_local.py")

# --- 1. Secret Key Validation ------------------------------------------------
SECRET_KEY = env('DJANGO_SECRET_KEY', default='')
_INSECURE_DEFAULTS = {
    'insecure-dev-key-change-me',
    'insecure-dev-only-secret-key-for-local-testing',
    'replace-with-a-long-random-secret-key-at-least-50-chars',
    ''
}
if not SECRET_KEY or SECRET_KEY in _INSECURE_DEFAULTS or len(SECRET_KEY) < 32:
    raise ImproperlyConfigured(
        'DJANGO_SECRET_KEY is missing, too short, or using an insecure default. '
        'Set a strong, unique DJANGO_SECRET_KEY environment variable (at least 32 characters) for production.'
    )

# --- 2. Allowed Hosts Validation ---------------------------------------------
ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS', default=[])
_INSECURE_HOSTS = {'*', 'localhost', '127.0.0.1', 'testserver'}
valid_hosts = [h for h in ALLOWED_HOSTS if h not in _INSECURE_HOSTS]
if not valid_hosts:
    raise ImproperlyConfigured(
        'DJANGO_ALLOWED_HOSTS must contain valid production hostnames. '
        'Localhost, testserver, and wildcard hosts are rejected in production.'
    )

# --- 3. Production Database (PostgreSQL) -------------------------------------
database_url = env('DATABASE_URL', default='')
if not database_url:
    raise ImproperlyConfigured(
        'DATABASE_URL environment variable is required for production (PostgreSQL).'
    )
if database_url.startswith('sqlite'):
    raise ImproperlyConfigured(
        'SQLite is not allowed in production. DATABASE_URL must point to PostgreSQL.'
    )
DATABASES['default'] = env.db('DATABASE_URL')  # noqa: F405

# --- 4. Distributed Cache / Channel Layer (Redis) ----------------------------
REDIS_URL = env('REDIS_URL', default='')
if not REDIS_URL:
    raise ImproperlyConfigured(
        'REDIS_URL environment variable is required for production (shared Channels and Cache).'
    )

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

# --- 5. Email Configuration --------------------------------------------------
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
if not EMAIL_HOST_PASSWORD:
    raise ImproperlyConfigured(
        'EMAIL_HOST_PASSWORD must be set in the production environment.'
    )

# --- 6. Reverse Proxy & Security Headers -------------------------------------
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = env.bool('DJANGO_SECURE_SSL_REDIRECT', default=True)
SESSION_COOKIE_SECURE = env.bool('DJANGO_SESSION_COOKIE_SECURE', default=True)
CSRF_COOKIE_SECURE = env.bool('DJANGO_CSRF_COOKIE_SECURE', default=True)
SECURE_HSTS_SECONDS = env.int('DJANGO_SECURE_HSTS_SECONDS', default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False)
SECURE_HSTS_PRELOAD = env.bool('DJANGO_SECURE_HSTS_PRELOAD', default=False)

CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# --- 7. Logging with Data Minimization ---------------------------------------
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

# --- 8. Static Storage -------------------------------------------------------
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# --- 9. WebAuthn Passkey Production Configuration ----------------------------
WEBAUTHN_RP_ID = env('WEBAUTHN_RP_ID', default=valid_hosts[0] if valid_hosts else '')
_INSECURE_RP_IDS = {'*', 'localhost', '127.0.0.1', 'testserver', ''}
if not WEBAUTHN_RP_ID or WEBAUTHN_RP_ID in _INSECURE_RP_IDS:
    raise ImproperlyConfigured('WEBAUTHN_RP_ID must be set to a valid production domain.')

WEBAUTHN_ALLOWED_ORIGINS = env.list(
    'WEBAUTHN_ALLOWED_ORIGINS',
    default=[f'https://{h}' for h in valid_hosts]
)
if not WEBAUTHN_ALLOWED_ORIGINS:
    raise ImproperlyConfigured('WEBAUTHN_ALLOWED_ORIGINS must contain valid production origins.')
for origin in WEBAUTHN_ALLOWED_ORIGINS:
    if not origin.startswith('https://'):
        raise ImproperlyConfigured(f'WebAuthn origin {origin} must use HTTPS in production.')
