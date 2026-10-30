"""
Environment detection and account utility helpers for Campus Nexus.
"""
from django.conf import settings


def is_test_environment() -> bool:
    """Return True if running under automated Django test runner."""
    import sys
    return bool(getattr(settings, 'TESTING', False) or ('test' in sys.argv))


def is_alpha_environment() -> bool:
    """Return True if running in alpha/staging pilot mode."""
    return bool(getattr(settings, 'ALPHA_MODE', False))


def is_production_environment() -> bool:
    """Return True if running in strict production mode."""
    return not getattr(settings, 'DEBUG', False) and not is_test_environment() and not is_alpha_environment()


def is_debug_enrollment(enrollment: str) -> bool:
    """Check if enrollment string is a synthetic debug enrollment (starts with 20XX)."""
    return bool(enrollment and str(enrollment).strip().upper().startswith('20XX'))


def is_debug_allowed() -> bool:
    """Return True if synthetic debug accounts are permitted in the current environment."""
    return bool(getattr(settings, 'DEBUG', False) or is_test_environment() or is_alpha_environment())
