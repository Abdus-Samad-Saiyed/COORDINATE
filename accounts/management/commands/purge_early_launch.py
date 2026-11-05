"""Management command to purge / delete the temporary early launch database."""

import os
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Purge the temporary early launch database (temp_early_access.sqlite3)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            dest='force',
            default=False,
            help='Purge temporary database without interactive confirmation',
        )

    def handle(self, *args, **options):
        temp_db_path = getattr(settings, 'EARLY_LAUNCH_DB_PATH', settings.BASE_DIR / 'temp_early_access.sqlite3')
        if not os.path.exists(temp_db_path):
            self.stdout.write(self.style.SUCCESS(f"No temporary database found at {temp_db_path}."))
            return

        if not options.get('force'):
            confirm = input(f"Are you sure you want to delete the temporary database at {temp_db_path}? (yes/no): ")
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING("Aborted."))
                return

        try:
            from django.db import connections
            for conn in connections.all():
                conn.close()
            os.remove(temp_db_path)
            self.stdout.write(self.style.SUCCESS(f"Successfully purged temporary database: {temp_db_path}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to purge temporary database: {e}"))
