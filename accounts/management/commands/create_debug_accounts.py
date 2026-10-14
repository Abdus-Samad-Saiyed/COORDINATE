"""Management command: create debug/test accounts for development."""

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from coordinate.models import RideParticipant, RideRequest

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
    },
]

DEBUG_PASSWORD = 'Debug@123'
PERSONAL_SUPERACCOUNT = {
    'enrollment_number': '2024BCSE065',
    'username': '2024BCSE065',
    'first_name': 'Abdus Samad',
    'last_name': 'Saiyed',
    'email': 'asaiyed_2024bcse065@nitsri.ac.in',
    'phone_number': '+917355463857',
    'gender': 'M',
    'is_superuser': True,
    'is_staff': True,
    'verified': True,
    'is_active': True,
}
PERSONAL_PASSWORD = 'AbSm72000@123'


class Command(BaseCommand):
    help = 'Purge legacy debug accounts, create 20XX branch debug accounts, and set up superaccount 2024BCSE065.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing debug accounts before recreating them.',
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                'This command can only be run with DEBUG=True. '
                'Refusing to create debug accounts in a production environment.'
            )

        # 1. Create or update personal superaccount: 2024BCSE065
        super_user, created_super = User.objects.get_or_create(
            enrollment_number=PERSONAL_SUPERACCOUNT['enrollment_number'],
            defaults={
                **PERSONAL_SUPERACCOUNT,
                'password': make_password(PERSONAL_PASSWORD),
            }
        )
        if not created_super:
            for k, v in PERSONAL_SUPERACCOUNT.items():
                setattr(super_user, k, v)
            super_user.set_password(PERSONAL_PASSWORD)
            super_user.save()
            self.stdout.write(self.style.SUCCESS(f'Updated superaccount {super_user.enrollment_number} (+917355463857)'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Created superaccount {super_user.enrollment_number} (+917355463857)'))

        # 2. Reassign rides and participations from 2024BCSE001 to 2024BCSE065 before deletion
        old_admin = User.objects.filter(enrollment_number='2024BCSE001').first()
        if old_admin:
            RideRequest.objects.filter(creator=old_admin).update(creator=super_user)
            # Reassign participations
            for p in RideParticipant.objects.filter(user=old_admin):
                if not RideParticipant.objects.filter(ride=p.ride, user=super_user).exists():
                    p.user = super_user
                    p.save(update_fields=['user'])
                else:
                    p.delete()
            old_admin.delete()
            self.stdout.write(self.style.WARNING('Dropped legacy superaccount 2024BCSE001 and migrated rides to 2024BCSE065.'))

        # 3. Clean up other legacy 2024 and 2099 debug accounts
        legacy_debug_enrollments = [
            '2024BCSE002', '2024BCSE003', '2024BECE004', '2024BECE005', '2024BCIV006',
            '2099BCSE001', '2099BCSE002', '2099BCSE003', '2099BECE004', '2099BECE005', '2099BCIV006',
            '2099BCSE999', '2099BCSE998', '2099BCSE997'
        ]
        deleted_legacy, _ = User.objects.filter(enrollment_number__in=legacy_debug_enrollments).delete()
        if deleted_legacy:
            self.stdout.write(self.style.WARNING(f'Purged {deleted_legacy} legacy debug account(s) using real student years.'))

        if options['reset']:
            debug_enrollments = [u['enrollment_number'] for u in DEBUG_USERS]
            deleted_reset, _ = User.objects.filter(enrollment_number__in=debug_enrollments).delete()
            self.stdout.write(self.style.WARNING(f'Reset {deleted_reset} existing 20XX debug account(s).'))

        # 4. Create 20XX branch debug accounts
        hashed_debug_pw = make_password(DEBUG_PASSWORD)
        created = 0
        skipped = 0

        for data in DEBUG_USERS:
            enrollment = data['enrollment_number']
            if User.objects.filter(enrollment_number=enrollment).exists():
                self.stdout.write(f'  SKIP  {enrollment} (already exists)')
                skipped += 1
                continue

            User.objects.create(**data, password=hashed_debug_pw)
            self.stdout.write(self.style.SUCCESS(f'  CREATE {enrollment} — {data["first_name"]} {data["last_name"]} ({data["phone_number"]})'))
            created += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Done. Created {created} 20XX debug accounts, skipped {skipped}.'
        ))
        self.stdout.write(self.style.SUCCESS(f'Active Superaccount: 2024BCSE065 / {PERSONAL_PASSWORD}'))

