import os
import sqlite3
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections
from accounts.models import User


class Command(BaseCommand):
    help = "Scan media storage and purge orphaned or fake profile pictures not referenced by any real user."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate cleanup without actually deleting any files.',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        profiles_dir = Path(settings.MEDIA_ROOT) / 'profiles'

        if not profiles_dir.exists():
            self.stdout.write(self.style.WARNING(f"Profiles directory does not exist: {profiles_dir}"))
            return

        # 1. Collect all valid profile photo references across all connected databases
        active_photos = set()
        active_basenames = set()

        for alias in connections:
            try:
                photos = (
                    User.objects.using(alias)
                    .exclude(profile_photo='')
                    .exclude(profile_photo__isnull=True)
                    .values_list('profile_photo', flat=True)
                )
                for p in photos:
                    if p:
                        active_photos.add(str(p).replace('\\', '/'))
                        active_basenames.add(Path(p).name)
            except Exception:
                pass

        # Also inspect local SQLite database files directly as safety net
        for db_file in [settings.BASE_DIR / 'db.sqlite3', settings.BASE_DIR / 'temp_early_access.sqlite3']:
            if db_file.exists():
                try:
                    conn = sqlite3.connect(str(db_file))
                    cur = conn.cursor()
                    cur.execute("SELECT profile_photo FROM accounts_user WHERE profile_photo IS NOT NULL AND profile_photo != ''")
                    for (p,) in cur.fetchall():
                        if p:
                            active_photos.add(str(p).replace('\\', '/'))
                            active_basenames.add(Path(p).name)
                    conn.close()
                except Exception:
                    pass

        self.stdout.write(
            f"Found {len(active_basenames)} active profile photo(s) in database records: {sorted(active_basenames)}"
        )

        # 2. Iterate through files in media/profiles/
        all_files = [f for f in profiles_dir.iterdir() if f.is_file()]
        preserved = []
        orphaned = []
        bytes_freed = 0

        for file_path in all_files:
            rel_name = f"profiles/{file_path.name}".replace('\\', '/')
            if rel_name in active_photos or file_path.name in active_basenames:
                preserved.append(file_path.name)
            else:
                orphaned.append(file_path)
                bytes_freed += file_path.stat().st_size

        self.stdout.write(f"Total files in {profiles_dir}: {len(all_files)}")
        self.stdout.write(f"Preserved active photos ({len(preserved)}): {preserved}")

        if not orphaned:
            self.stdout.write(self.style.SUCCESS("No orphaned or fake profile pictures found. Storage is clean!"))
            return

        self.stdout.write(
            self.style.NOTICE(
                f"Identified {len(orphaned)} orphaned/fake file(s) ({bytes_freed / 1024:.1f} KB)."
            )
        )

        for file_path in orphaned:
            if dry_run:
                self.stdout.write(f"  [DRY-RUN] Would delete: {file_path.name}")
            else:
                try:
                    file_path.unlink()
                    self.stdout.write(f"  [DELETED] {file_path.name}")
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f"  [ERROR] Could not delete {file_path.name}: {exc}"))

        if dry_run:
            self.stdout.write(self.style.WARNING(f"\nDry run complete. No files were removed. Run without --dry-run to purge."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSuccessfully purged {len(orphaned)} orphaned file(s). Freed {bytes_freed / 1024:.1f} KB. Preserved {len(preserved)} active user photo(s)."
                )
            )
