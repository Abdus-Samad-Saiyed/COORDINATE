"""Test settings configuration for Campus Nexus.

Optimized for fast, isolated, deterministic test suite execution.
- In-memory database & cache
- In-memory channel layer (no external Redis dependency required for unit tests)
- Fast MD5 password hasher (10x faster unit tests)
- In-memory locmem email backend
- DEBUG is False to verify production-like view branching
"""

from .base import *

DEBUG = False
TESTING = True

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

DATABASES = {
    'default': env.db('TEST_DATABASE_URL', default='sqlite:///:memory:')
}

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'campus-nexus-test-cache',
    }
}
