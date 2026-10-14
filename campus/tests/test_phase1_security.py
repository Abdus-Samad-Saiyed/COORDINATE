"""Phase 1 regression tests — security hardening & housekeeping.

Tests cover:
  SEC-08: create_debug_accounts refuses to run when DEBUG=False
  SEC-09: Production settings raise on missing/placeholder SECRET_KEY
  DUMP-01: dump_project.py excludes sensitive files
  DEP-02: .dockerignore excludes secrets
  LIC-01: LICENSE file exists and is MIT
"""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings


# ---------------------------------------------------------------------------
# Resolve project root (parent of 'campus/' package)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class DebugAccountsProductionGuardTest(TestCase):
    """SEC-08: create_debug_accounts must refuse to run when DEBUG=False."""

    @override_settings(DEBUG=False)
    def test_refuses_when_debug_false(self):
        with self.assertRaises(CommandError) as ctx:
            call_command('create_debug_accounts')
        self.assertIn('DEBUG=True', str(ctx.exception))

    @override_settings(DEBUG=True)
    def test_runs_when_debug_true(self):
        """Command executes successfully when DEBUG=True."""
        # Should not raise — just run it.
        call_command('create_debug_accounts')


class DebugAccountsResetGuardTest(TestCase):
    """SEC-08: --reset flag also refuses under production."""

    @override_settings(DEBUG=False)
    def test_reset_refuses_when_debug_false(self):
        with self.assertRaises(CommandError):
            call_command('create_debug_accounts', '--reset')


class DebugAccountsNoPasswordLeakTest(TestCase):
    """SEC-07: The command must not print the raw password to stdout."""

    @override_settings(DEBUG=True)
    def test_no_plaintext_password_in_output(self):
        from io import StringIO
        out = StringIO()
        call_command('create_debug_accounts', stdout=out)
        output = out.getvalue()
        self.assertNotIn('Debug@123', output)


class ProductionSecretKeyValidationTest(unittest.TestCase):
    """SEC-09: prod.py must raise ValueError on insecure/missing SECRET_KEY."""

    def test_insecure_default_raises(self):
        """Importing prod settings with the placeholder key must raise."""
        import importlib
        import campus.settings.base as base_module

        original_key = base_module.SECRET_KEY
        try:
            base_module.SECRET_KEY = 'insecure-dev-key-change-me'

            # Force fresh import of prod module
            import sys
            sys.modules.pop('campus.settings.prod', None)

            with self.assertRaises(ValueError) as ctx:
                import campus.settings.prod  # noqa: F401
            self.assertIn('DJANGO_SECRET_KEY', str(ctx.exception))
        finally:
            base_module.SECRET_KEY = original_key
            import sys
            sys.modules.pop('campus.settings.prod', None)

    def test_empty_key_raises(self):
        """Empty string SECRET_KEY must also raise."""
        import importlib
        import campus.settings.base as base_module

        original_key = base_module.SECRET_KEY
        try:
            base_module.SECRET_KEY = ''

            import sys
            sys.modules.pop('campus.settings.prod', None)

            with self.assertRaises(ValueError):
                import campus.settings.prod  # noqa: F401
        finally:
            base_module.SECRET_KEY = original_key
            import sys
            sys.modules.pop('campus.settings.prod', None)

    def test_real_key_does_not_raise(self):
        """A real secret key must not trigger the guard."""
        import importlib
        import campus.settings.base as base_module

        original_key = base_module.SECRET_KEY
        try:
            base_module.SECRET_KEY = 'a-real-production-secret-key-that-is-long-enough'

            import sys
            sys.modules.pop('campus.settings.prod', None)

            # This should NOT raise
            import campus.settings.prod  # noqa: F401
        finally:
            base_module.SECRET_KEY = original_key
            import sys
            sys.modules.pop('campus.settings.prod', None)


class DumpToolExclusionTest(unittest.TestCase):
    """DUMP-01: dump_project.py must exclude sensitive files."""

    def test_excluded_files_set_contains_secrets(self):
        """Verify the EXCLUDED_FILES constant blocks known sensitive files."""
        # Import the module's exclusion sets directly
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'dump_project',
            PROJECT_ROOT / 'dump_project.py',
        )
        mod = importlib.util.module_from_spec(spec)

        # We need to prevent the script from actually running (it writes a
        # file at import time). Patch open and print.
        import builtins
        from unittest.mock import mock_open
        with patch.object(builtins, 'open', mock_open()), \
             patch('builtins.print'):
            spec.loader.exec_module(mod)

        sensitive = {'.env', 'debug_accounts.md', 'superuser_password', 'db.sqlite3'}
        for name in sensitive:
            self.assertIn(name, mod.EXCLUDED_FILES, f'{name} missing from EXCLUDED_FILES')

    def test_excluded_dirs_blocks_venv_and_media(self):
        """Verify venv, media, staticfiles dirs are excluded."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'dump_project',
            PROJECT_ROOT / 'dump_project.py',
        )
        mod = importlib.util.module_from_spec(spec)

        import builtins
        from unittest.mock import mock_open
        with patch.object(builtins, 'open', mock_open()), \
             patch('builtins.print'):
            spec.loader.exec_module(mod)

        for d in ('venv', '.venv', 'media', 'staticfiles'):
            self.assertIn(d, mod.EXCLUDED_DIRS, f'{d} missing from EXCLUDED_DIRS')

    def test_should_skip_file_catches_sensitive_names(self):
        """should_skip_file() returns True for known sensitive filenames."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'dump_project',
            PROJECT_ROOT / 'dump_project.py',
        )
        mod = importlib.util.module_from_spec(spec)

        import builtins
        from unittest.mock import mock_open
        with patch.object(builtins, 'open', mock_open()), \
             patch('builtins.print'):
            spec.loader.exec_module(mod)

        self.assertTrue(mod.should_skip_file('.env'))
        self.assertTrue(mod.should_skip_file('debug_accounts.md'))
        self.assertTrue(mod.should_skip_file('superuser_password'))
        self.assertTrue(mod.should_skip_file('db.sqlite3'))


class DockerIgnoreTest(unittest.TestCase):
    """DEP-02: .dockerignore must exclude secrets and generated files."""

    def setUp(self):
        dockerignore_path = PROJECT_ROOT / '.dockerignore'
        self.assertTrue(dockerignore_path.exists(), '.dockerignore file must exist')
        self.content = dockerignore_path.read_text()

    def test_env_excluded(self):
        self.assertIn('.env', self.content)

    def test_debug_accounts_excluded(self):
        self.assertIn('debug_accounts.md', self.content)

    def test_sqlite_excluded(self):
        # Should match either *.sqlite3 or db.sqlite3
        self.assertTrue(
            '*.sqlite3' in self.content or 'db.sqlite3' in self.content,
        )

    def test_venv_excluded(self):
        self.assertIn('venv/', self.content)

    def test_pycache_excluded(self):
        self.assertIn('__pycache__', self.content)


class LicenseFileTest(unittest.TestCase):
    """LIC-01: MIT LICENSE file must exist with correct content."""

    def setUp(self):
        self.license_path = PROJECT_ROOT / 'LICENSE'

    def test_license_exists(self):
        self.assertTrue(self.license_path.exists(), 'LICENSE file must exist')

    def test_license_is_mit(self):
        content = self.license_path.read_text()
        self.assertIn('MIT License', content)
        self.assertIn('Permission is hereby granted', content)

    def test_license_has_attribution(self):
        content = self.license_path.read_text()
        self.assertIn('Abdus Samad Saiyed', content)


class GitIgnoreTest(unittest.TestCase):
    """SEC-07: .gitignore must exclude debug_accounts.md."""

    def setUp(self):
        self.content = (PROJECT_ROOT / '.gitignore').read_text()

    def test_debug_accounts_excluded(self):
        self.assertIn('debug_accounts.md', self.content)

    def test_env_excluded(self):
        self.assertIn('.env', self.content)

    def test_media_excluded(self):
        self.assertIn('media/', self.content)


class ApplicationStartsWithTestSettingsTest(TestCase):
    """Verify the application starts with safe test settings."""

    def test_django_check_passes(self):
        """Django system checks must pass (called via management command)."""
        from io import StringIO
        call_command('check', stdout=StringIO())
