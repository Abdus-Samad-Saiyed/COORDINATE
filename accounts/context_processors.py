"""Context processors for accounts application."""

from django.conf import settings


def early_launch_context(request):
    """Expose early_launch_mode boolean flag across all templates."""
    return {
        'early_launch_mode': getattr(settings, 'EARLY_LAUNCH_MODE', False)
    }
