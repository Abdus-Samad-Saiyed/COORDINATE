"""Extended Daphne runserver management command with --early-launch support.

Enables instant student self-declaration (enrollment + phone number) without
requiring in-person physical admin verification.
"""

import os
from django.conf import settings
from daphne.management.commands.runserver import Command as DaphneRunserverCommand


class Command(DaphneRunserverCommand):
    """Runserver command supporting the --early-launch flag."""

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            '--early-launch',
            action='store_true',
            dest='early_launch',
            default=False,
            help='Run server in Early Launch Mode (instant student self-declaration, skips physical verification)',
        )

    def handle(self, *args, **options):
        if options.get('early_launch'):
            os.environ['CAMPUS_EARLY_LAUNCH_MODE'] = 'True'
            settings.EARLY_LAUNCH_MODE = True
            self.stdout.write(self.style.WARNING(
                "\n" + "=" * 70 + "\n"
                "CAMPUS NEXUS — EARLY LAUNCH MODE ACTIVE\n"
                "  * Physical verification desk requirements bypassed.\n"
                "  * Student self-declaration active (Enrollment + Phone Number).\n"
                "  * Instant account activation & full COORDINATE access enabled.\n"
                + "=" * 70 + "\n"
            ))
        super().handle(*args, **options)
