"""Management command to purge / delete the temporary early launch database."""

import os
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone


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

        # Check for active scheduled rides before purging to prevent ghost/orphaned rides
        self._check_active_rides()

        if not options.get('force'):
            confirm = input(f"Are you sure you want to delete the temporary database at {temp_db_path}? (yes/no): ")
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING("Aborted."))
                return

        try:
            from django.db import connections, models
            from accounts.models import Friendship, FriendRequest
            for db_name in ['permanent', 'default']:
                if db_name in connections:
                    try:
                        deleted_fr, _ = FriendRequest.objects.using(db_name).filter(
                            models.Q(sender__verified=False) | models.Q(receiver__verified=False)
                        ).delete()
                        deleted_fs, _ = Friendship.objects.using(db_name).filter(
                            models.Q(user1__verified=False) | models.Q(user2__verified=False)
                        ).delete()
                        if deleted_fr or deleted_fs:
                            self.stdout.write(self.style.SUCCESS(
                                f"Scrubbed {deleted_fs} temporary friendships and {deleted_fr} temporary friend requests from '{db_name}' database."
                            ))
                    except Exception:
                        pass

            for conn in connections.all():
                conn.close()
            os.remove(temp_db_path)
            self.stdout.write(self.style.SUCCESS(f"Successfully purged temporary database: {temp_db_path}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to purge temporary database: {e}"))

    def _check_active_rides(self):
        """Warn if upcoming rides exist in temporary database to prevent softlocked journeys."""
        from django.db import connections
        from coordinate.models import RideRequest
        try:
            db_alias = 'default' if getattr(settings, 'EARLY_LAUNCH_MODE', False) else 'temp_early_access'
            if db_alias in connections:
                active_rides = RideRequest.objects.using(db_alias).filter(
                    status__in=['OPEN', 'FULL'],
                    departure_time__gt=timezone.now()
                )
                count = active_rides.count()
                if count > 0:
                    self.stdout.write(self.style.WARNING(
                        f"\n⚠️  ACTIVE RIDE WARNING: There are {count} upcoming scheduled rides in the temporary database that have not departed yet!"
                    ))
                    for r in active_rides[:5]:
                        self.stdout.write(f"  * Ride #{r.id}: {r.get_route_display()} — Departs {r.departure_time} ({r.participant_count} passengers)")
                    self.stdout.write(self.style.WARNING("Purging now will erase these active rides.\n"))
        except Exception:
            pass
