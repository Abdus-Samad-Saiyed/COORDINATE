"""Management command: create debug/test accounts for development."""

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand

from accounts.models import User

DEBUG_USERS = [
    {
        'enrollment_number': '2024BCSE001',
        'username': '2024BCSE001',
        'first_name': 'Abdus',
        'last_name': 'Samad',
        'phone_number': '+919876543210',
        'gender': 'M',
        'is_superuser': True,
        'is_staff': True,
        'verified': True,
    },
    {
        'enrollment_number': '2024BCSE002',
        'username': '2024BCSE002',
        'first_name': 'Raza',
        'last_name': 'Khan',
        'phone_number': '+919876543211',
        'gender': 'M',
        'verified': True,
    },
    {
        'enrollment_number': '2024BCSE003',
        'username': '2024BCSE003',
        'first_name': 'Aisha',
        'last_name': 'Wani',
        'phone_number': '+919876543212',
        'gender': 'F',
        'verified': True,
    },
    {
        'enrollment_number': '2024BECE004',
        'username': '2024BECE004',
        'first_name': 'Umar',
        'last_name': 'Farooq',
        'phone_number': '+919876543213',
        'gender': 'M',
        'verified': True,
    },
    {
        'enrollment_number': '2024BECE005',
        'username': '2024BECE005',
        'first_name': 'Fatima',
        'last_name': 'Sheikh',
        'phone_number': '+919876543214',
        'gender': 'F',
        'verified': True,
    },
    {
        'enrollment_number': '2024BCIV006',
        'username': '2024BCIV006',
        'first_name': 'Bilal',
        'last_name': 'Ahmad',
        'phone_number': '+919876543215',
        'gender': 'M',
        'verified': True,
    },
]

DEBUG_PASSWORD = 'Debug@123'


class Command(BaseCommand):
    help = 'Create debug accounts for local development and testing.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing debug accounts before recreating them.',
        )

    def handle(self, *args, **options):
        hashed_password = make_password(DEBUG_PASSWORD)

        if options['reset']:
            enrollments = [u['enrollment_number'] for u in DEBUG_USERS]
            deleted, _ = User.objects.filter(enrollment_number__in=enrollments).delete()
            self.stdout.write(self.style.WARNING(f'Deleted {deleted} existing debug account(s).'))

        created = 0
        skipped = 0

        for data in DEBUG_USERS:
            enrollment = data['enrollment_number']
            if User.objects.filter(enrollment_number=enrollment).exists():
                self.stdout.write(f'  SKIP  {enrollment} (already exists)')
                skipped += 1
                continue

            User.objects.create(**data, password=hashed_password)
            self.stdout.write(self.style.SUCCESS(f'  CREATE {enrollment} — {data["first_name"]} {data["last_name"]}'))
            created += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Done. Created {created}, skipped {skipped}.'
        ))
        self.stdout.write(f'Password for all accounts: {DEBUG_PASSWORD}')
