from django.core.checks import Error, register
from django.conf import settings


@register('security', 'deployment')
def check_debug_accounts_safety(app_configs, **kwargs):
    """
    Ensure no synthetic debug accounts (20XX...) are active in non-debug/non-test environments.
    """
    errors = []
    from accounts.utils import is_debug_allowed
    if not is_debug_allowed():
        try:
            from django.db import connection
            if 'accounts_user' in connection.introspection.table_names():
                from django.contrib.auth import get_user_model
                User = get_user_model()
                if User.objects.filter(enrollment_number__startswith='20XX', is_active=True).exists():
                    errors.append(
                        Error(
                            "Active synthetic debug accounts (20XX...) detected in non-debug/non-test environment!",
                            hint="Deactivate or purge 20XX accounts before deploying to staging or production.",
                            id="accounts.E001",
                        )
                    )
        except Exception:
            # If database is unreachable during certain check phases, pass quietly
            pass
    return errors
