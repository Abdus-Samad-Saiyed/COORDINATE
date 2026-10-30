"""Stage 7 tests — Production Database, Cache, and Operational Lifecycle.

Covers:
1. Operational /health/ endpoint response format (JSON and HTML) and status reporting.
2. Health check database failure graceful degradation (503 Service Unavailable).
3. Cache probe verification in health check.
4. Production settings fail-safes (Postgres requirement, Redis channel layers, host validation).
"""

import importlib
import os
import sys
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse


class Stage7HealthCheckEndpointTests(TestCase):
    """Test system operational health check endpoint."""

    def test_health_check_json_success(self):
        """GET /health/ returns 200 with healthy database, cache, and telemetry."""
        response = self.client.get(reverse('health_check'), HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = response.json()
        self.assertEqual(data.get('status'), 'healthy')
        self.assertEqual(data.get('database'), 'connected')
        self.assertEqual(data.get('cache'), 'connected')
        self.assertIn('version', data)
        self.assertIn('traffic_telemetry', data)

    def test_health_check_html_rendering(self):
        """GET /health/?format=html renders the dashboard HTML view."""
        response = self.client.get(reverse('health_check') + '?format=html')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response['Content-Type'])
        self.assertContains(response, 'System Health')
        self.assertContains(response, 'ALL SYSTEMS OPERATIONAL')

    def test_health_check_database_failure_returns_503(self):
        """Simulated database connection failure triggers 503 Service Unavailable."""
        with patch('django.db.connection.cursor', side_effect=Exception("Database connection timeout")):
            response = self.client.get(reverse('health_check'), HTTP_ACCEPT='application/json')
            self.assertEqual(response.status_code, 503)
            data = response.json()
            self.assertEqual(data.get('status'), 'unhealthy')
            self.assertEqual(data.get('database'), 'disconnected')
            self.assertIn('error', data)


class Stage7ProductionConfigFailSafeTests(SimpleTestCase):
    """Test production settings fail-safe validation rules."""

    def setUp(self):
        self._saved_modules = {
            'secrets_local': sys.modules.get('campus.settings.secrets_local'),
            'prod': sys.modules.get('campus.settings.prod'),
        }
        sys.modules.pop('campus.settings.secrets_local', None)
        sys.modules.pop('campus.settings.prod', None)

    def tearDown(self):
        for name, mod in self._saved_modules.items():
            key = 'campus.settings.' + name
            if mod is not None:
                sys.modules[key] = mod
            else:
                sys.modules.pop(key, None)

    def test_production_rejects_sqlite(self):
        """Production settings fail if DATABASE_URL is SQLite."""
        test_env = {
            'DJANGO_SECRET_KEY': 'a' * 50,
            'DJANGO_ALLOWED_HOSTS': 'campusnexus.nitsri.ac.in',
            'DATABASE_URL': 'sqlite:///db.sqlite3',
            'REDIS_URL': 'redis://127.0.0.1:6379/0',
            'EMAIL_HOST_PASSWORD': 'dummy_password',
        }
        with patch.dict(os.environ, test_env, clear=True):
            sys.modules.pop('campus.settings.prod', None)
            with self.assertRaises(ValueError) as ctx:
                importlib.import_module('campus.settings.prod')
            self.assertIn('SQLite is not allowed in production', str(ctx.exception))

    def test_production_requires_redis_url(self):
        """Production settings fail if REDIS_URL is missing."""
        test_env = {
            'DJANGO_SECRET_KEY': 'a' * 50,
            'DJANGO_ALLOWED_HOSTS': 'campusnexus.nitsri.ac.in',
            'DATABASE_URL': 'postgres://user:pass@localhost:5432/campus_db',
            'EMAIL_HOST_PASSWORD': 'dummy_password',
        }
        with patch.dict(os.environ, test_env, clear=True):
            sys.modules.pop('campus.settings.prod', None)
            with self.assertRaises(ValueError) as ctx:
                importlib.import_module('campus.settings.prod')
            self.assertIn('REDIS_URL environment variable is required', str(ctx.exception))
