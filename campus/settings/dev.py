from .base import *  # noqa: F401, F403

DEBUG = True

# Use in-memory channel layer for dev when Redis isn't running.
# Comment this out and set REDIS_URL in .env to use Redis locally.
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# Show emails in the console during development.
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
