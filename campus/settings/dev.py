from .base import *  # noqa: F401, F403

DEBUG = True

# Import local untracked development secrets if present
try:
    from . import secrets_local
    for attr in dir(secrets_local):
        if not attr.startswith('_'):
            val = getattr(secrets_local, attr)
            # Environment variables take precedence if already populated
            if attr == 'DJANGO_SECRET_KEY' and not env('DJANGO_SECRET_KEY', default=''):
                SECRET_KEY = val
            elif attr == 'EMAIL_HOST_PASSWORD' and not env('EMAIL_HOST_PASSWORD', default=''):
                EMAIL_HOST_PASSWORD = val
            elif attr == 'EMAIL_HOST_USER' and not env('EMAIL_HOST_USER', default=''):
                EMAIL_HOST_USER = val
            elif not hasattr(globals(), attr) or getattr(globals(), attr) == '':
                globals()[attr] = val
except ImportError:
    pass

# Safe development fallback for SECRET_KEY if still empty
if not SECRET_KEY or SECRET_KEY == 'insecure-dev-key-change-me':
    SECRET_KEY = 'insecure-dev-only-secret-key-for-local-testing'

# Use in-memory channel layer for dev when Redis isn't running.
# Set REDIS_URL in .env or secrets_local.py to use Redis locally.
if not env('REDIS_URL', default=''):
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

# Email configuration:
# Uses SMTP if EMAIL_HOST_PASSWORD is provided, otherwise falls back to console in dev.
if EMAIL_HOST_PASSWORD and EMAIL_HOST_USER:
    EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
else:
    EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
