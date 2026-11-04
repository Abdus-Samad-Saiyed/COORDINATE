"""Django management command: launch interactive database setup and inspection."""

from django.core.management.base import BaseCommand
from scripts.setup_db import main


class Command(BaseCommand):
    help = "Launch interactive database setup, migrations, inspection, and user provisioning."

    def add_arguments(self, parser):
        parser.add_argument("--migrate", action="store_true", help="Apply unapplied migrations non-interactively")
        parser.add_argument("--check-migrations", action="store_true", help="Check for unapplied migrations")
        parser.add_argument("--add-user", action="store_true", help="Non-interactive user creation")
        parser.add_argument("--enrollment", type=str, help="Enrollment number for user")
        parser.add_argument("--password", type=str, help="Password for user")
        parser.add_argument("--email", type=str, help="Email address")
        parser.add_argument("--first-name", type=str, default="Campus", help="First name")
        parser.add_argument("--last-name", type=str, default="User", help="Last name")
        parser.add_argument("--phone", type=str, default="+919876543210", help="Phone number")
        parser.add_argument("--gender", type=str, default="M", choices=["M", "F"], help="Gender (M/F)")
        parser.add_argument("--admin", action="store_true", help="Create as superuser and staff")
        parser.add_argument("--staff", action="store_true", help="Create as staff")
        parser.add_argument("--verified", action="store_true", default=True, help="Mark user as verified")

    def handle(self, *args, **options):
        main()
