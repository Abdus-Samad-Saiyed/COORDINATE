"""Context processors for accounts application."""

from django.conf import settings


def early_launch_context(request):
    """Expose early_launch_mode and pending application state across all templates."""
    pending_app = None
    user = getattr(request, 'user', None)
    if user and user.is_authenticated and not getattr(user, 'verified', False):
        try:
            from accounts.models import AccountApplication
            pending_app = AccountApplication.objects.filter(
                enrollment_number=user.enrollment_number,
                approved=False,
            ).first()
        except Exception:
            pass

    return {
        'early_launch_mode': getattr(settings, 'EARLY_LAUNCH_MODE', False),
        'pending_permanent_application': pending_app,
    }
