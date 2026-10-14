from .base import *  # noqa: F401, F403

DEBUG = True

# Use in-memory channel layer for dev when Redis isn't running.
# Comment this out and set REDIS_URL in .env to use Redis locally.
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# Email configuration:
# Defaults to console backend in dev if no SMTP credentials are provided.
# If EMAIL_HOST is configured (via .env or environment variables), switches to SMTP backend.
if env('EMAIL_HOST', default=''):
    EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
else:
    EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')


