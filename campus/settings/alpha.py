"""
Alpha / Staging settings for Campus Nexus.
Used for on-campus pilot and staging validation.
DEBUG is False, but ALPHA_MODE = True permits pilot telemetry and staging diagnostics.
"""
import environ
from .base import *  # noqa: F401, F403

DEBUG = False
ALPHA_MODE = True

env = environ.Env()

SECRET_KEY = env('DJANGO_SECRET_KEY', default='alpha-testing-secret-key-must-be-configured-for-deployment')

ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS', default=['localhost', '127.0.0.1', 'alpha.campusnexus.internal'])

# Email backend: SMTP if credentials provided, else console
if env('EMAIL_HOST_PASSWORD', default=''):
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Use Redis if available, fallback to locmem/inmemory
redis_url = env('REDIS_URL', default='')
if redis_url:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {'hosts': [redis_url]},
        },
    }
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': redis_url,
        }
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'alpha-cache',
        }
    }
