"""Management command: create debug/test accounts for development."""

import os
import secrets

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User

DEBUG_USERS = [
    {
        'enrollment_number': '20XXBCSE001',
        'username': '20XXBCSE001',
        'first_name': 'Debug CSE',
        'last_name': 'Student',
        'email': '20xxbcse001@nitsri.ac.in',
        'phone_number': '+919876543210',
        'gender': 'M',
        'verified': True,
        'is_active': True,
        'two_factor_enabled': False,
    },
    {
        'enrollment_number': '20XXBECE001',
        'username': '20XXBECE001',
        'first_name': 'Debug ECE',
        'last_name': 'Student',
        'email': '20xxbece001@nitsri.ac.in',
        'phone_number': '+919876543211',
        'gender': 'F',
        'verified': True,
        'is_active': True,
        'two_factor_enabled': False,
    },
    {
        'enrollment_number': '20XXBCIV001',
        'username': '20XXBCIV001',
        'first_name': 'Debug Civil',
        'last_name': 'Student',
        'email': '20xxbciv001@nitsri.ac.in',
        'phone_number': '+919876543212',
        'gender': 'M',
        'verified': True,
        'is_active': True,
        'two_factor_enabled': False,
    },
    {
        'enrollment_number': '20XXBELE001',
        'username': '20XXBELE001',
        'first_name': 'Debug Electrical',
        'last_name': 'Student',
        'email': '20xxbele001@nitsri.ac.in',
        'phone_number': '+919876543213',
        'gender': 'F',
        'verified': True,
        'is_active': True,
        'two_factor_enabled': False,
    },
    {
        'enrollment_number': '20XXBMEC001',
        'username': '20XXBMEC001',
        'first_name': 'Debug Mechanical',
        'last_name': 'Student',
        'email': '20xxbmec001@nitsri.ac.in',
        'phone_number': '+919876543214',
        'gender': 'M',
        'verified': True,
        'is_active': True,
        'two_factor_enabled': False,
    },
]

DEBUG_PASSWORD = os.environ.get('DEBUG_ACCOUNT_PASSWORD')
PERSONAL_SUPERACCOUNT_ENROLLMENT = os.environ.get('PERSONAL_SUPERACCOUNT_ENROLLMENT')
PERSONAL_PASSWORD = os.environ.get('PERSONAL_SUPERACCOUNT_PASSWORD')


class Command(BaseCommand):
    help = 'Create 20XX branch debug accounts and set up superaccount for development/testing.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing 20XX debug accounts before recreating them.',
        )
        parser.add_argument(
            '--reset-superuser',
            action='store_true',
            help='Overwrite existing personal superaccount password and attributes.',
        )

    def handle(self, *args, **options):
        if not getattr(settings, 'DEBUG', False):
            raise CommandError(
                'This command can only be run with DEBUG=True. '
                'Refusing to create debug accounts in a production environment.'
            )

        # 1. Create personal superaccount if configured in environment / settings
        super_user = None
        super_enrollment = PERSONAL_SUPERACCOUNT_ENROLLMENT or getattr(settings, 'PERSONAL_SUPERACCOUNT_ENROLLMENT', None)
        super_pw = PERSONAL_PASSWORD or getattr(settings, 'PERSONAL_SUPERACCOUNT_PASSWORD', None)

        if super_enrollment and super_pw:
            personal_account_data = {
                'enrollment_number': super_enrollment,
                'username': super_enrollment,
                'first_name': os.environ.get('PERSONAL_SUPERACCOUNT_FIRST_NAME') or getattr(settings, 'PERSONAL_SUPERACCOUNT_FIRST_NAME', 'Campus'),
                'last_name': os.environ.get('PERSONAL_SUPERACCOUNT_LAST_NAME') or getattr(settings, 'PERSONAL_SUPERACCOUNT_LAST_NAME', 'Admin'),
                'email': os.environ.get('PERSONAL_SUPERACCOUNT_EMAIL') or getattr(settings, 'PERSONAL_SUPERACCOUNT_EMAIL', f'{super_enrollment.lower()}@nitsri.ac.in'),
                'phone_number': os.environ.get('PERSONAL_SUPERACCOUNT_PHONE') or getattr(settings, 'PERSONAL_SUPERACCOUNT_PHONE', '+919999999999'),
                'gender': 'M',
                'is_superuser': True,
                'is_staff': True,
                'verified': True,
                'is_active': True,
                'two_factor_enabled': False,
            }
            super_user, created_super = User.objects.get_or_create(
                enrollment_number=super_enrollment,
                defaults={
                    **personal_account_data,
                    'password': make_password(super_pw),
                }
            )
            if not created_super:
                if options.get('reset_superuser'):
                    for k, v in personal_account_data.items():
                        setattr(super_user, k, v)
                    super_user.set_password(super_pw)
                    super_user.save()
                    self.stdout.write(self.style.SUCCESS(f'Reset superaccount {super_user.enrollment_number}'))
                else:
                    self.stdout.write(f'Superaccount {super_user.enrollment_number} already exists; preserving credentials.')
            else:
                self.stdout.write(self.style.SUCCESS(f'Created superaccount {super_user.enrollment_number}'))
        else:
            self.stdout.write('PERSONAL_SUPERACCOUNT not configured; skipping superaccount creation.')

        if options['reset']:
            debug_enrollments = [u['enrollment_number'] for u in DEBUG_USERS]
            deleted_reset, _ = User.objects.filter(enrollment_number__in=debug_enrollments).delete()
            self.stdout.write(self.style.WARNING(f'Reset {deleted_reset} existing 20XX debug account(s).'))

        # 2. Create 20XX branch debug accounts
        resolved_debug_pw = DEBUG_PASSWORD or getattr(settings, 'DEBUG_ACCOUNT_PASSWORD', None)
        if not resolved_debug_pw:
            resolved_debug_pw = secrets.token_urlsafe(16)
        hashed_debug_pw = make_password(resolved_debug_pw)
        created = 0
        skipped = 0

        for data in DEBUG_USERS:
            enrollment = data['enrollment_number']
            if User.objects.filter(enrollment_number=enrollment).exists():
                self.stdout.write(f'  SKIP  {enrollment} (already exists)')
                skipped += 1
                continue

            User.objects.create(**data, password=hashed_debug_pw)
            self.stdout.write(self.style.SUCCESS(f'  CREATE {enrollment} — {data["first_name"]} {data["last_name"]}'))
            created += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Done. Created {created} 20XX debug accounts, skipped {skipped}.'
        ))
        if super_user:
            self.stdout.write(self.style.SUCCESS(f'Active Superaccount configured: {super_user.enrollment_number} (superuser credentials provisioned).'))
