from datetime import timedelta
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class MigrationConsolidationTests(TransactionTestCase):
    migrate_from = [
        ('accounts', '0010_directmessage_idx_dm_sender_rcpt_created_and_more'),
        ('coordinate', '0011_alter_rideparticipant_options_and_more'),
    ]
    migrate_to = [
        ('accounts', '0010_directmessage_idx_dm_sender_rcpt_created_and_more'),
        ('coordinate', '0012_consolidate_ride_participation_data'),
    ]

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        # Migrate backwards to before data migration
        self.executor.migrate(self.migrate_from)
        self.executor.loader.build_graph()
        old_apps = self.executor.loader.project_state(self.migrate_from).apps

        User = old_apps.get_model('accounts', 'User')
        RideRequest = old_apps.get_model('coordinate', 'RideRequest')
        RideParticipant = old_apps.get_model('coordinate', 'RideParticipant')
        RideWaitlist = old_apps.get_model('coordinate', 'RideWaitlist')
        RideJoinRequest = old_apps.get_model('coordinate', 'RideJoinRequest')
        RideConsent = old_apps.get_model('coordinate', 'RideConsent')

        def make_user(username, enrollment, phone, gender='M'):
            return User.objects.create(
                username=username,
                enrollment_number=enrollment,
                gender=gender,
                phone_number=phone,
                show_friends_publicly=True,
                hide_online_status=False,
                hide_from_search=False,
                hide_profile_photo=False,
                show_contact_on_profile=False,
                verified=True,
            )

        # Create test users
        self.host = make_user('m_host', '2024BCSE301', '9876543301')
        self.passenger_consented = make_user('m_p1', '2024BCSE302', '9876543302')
        self.passenger_unconsented = make_user('m_p2', '2024BCSE303', '9876543303', gender='F')
        self.waitlisted_user = make_user('m_wl', '2024BCSE304', '9876543304')
        self.pending_user = make_user('m_pend', '2024BCSE305', '9876543305')
        self.coexisting_user = make_user('m_coex', '2024BCSE306', '9876543306')
        self.kicked_user = make_user('m_kick', '2024BCSE307', '9876543307')

        # Create ride
        self.ride = RideRequest.objects.create(
            creator=self.host,
            route='NIT_TO_AIRPORT',
            visibility='MIXED',
            departure_time=timezone.now() + timedelta(days=2),
            total_spots=4,
        )

        # 1. Host in RideParticipant (no consent row)
        RideParticipant.objects.create(ride=self.ride, user=self.host, status='CONFIRMED')

        # 2. Passenger with explicit consent
        RideParticipant.objects.create(ride=self.ride, user=self.passenger_consented, status='CONFIRMED')
        RideConsent.objects.create(
            ride=self.ride, user=self.passenger_consented,
            disclose_ride_identity=True, share_contact_details=True, is_revoked=False
        )

        # 3. Passenger with NO consent row
        RideParticipant.objects.create(ride=self.ride, user=self.passenger_unconsented, status='CONFIRMED')

        # 4. Standby waitlist user
        RideWaitlist.objects.create(ride=self.ride, user=self.waitlisted_user)

        # 5. Pending join request
        RideJoinRequest.objects.create(ride=self.ride, user=self.pending_user, status='PENDING', note='Wait for me')

        # 6. Coexisting user: in both RideParticipant AND left_users (CONFIRMED must win!)
        RideParticipant.objects.create(ride=self.ride, user=self.coexisting_user, status='CONFIRMED')
        self.ride.left_users.add(self.coexisting_user)

        # 7. Kicked user in kicked_users M2M
        self.ride.kicked_users.add(self.kicked_user)

    def test_migration_deduplication_and_consent_backfill(self):
        # Refresh migration executor before migrating forward
        self.executor = MigrationExecutor(connection)
        self.executor.loader.build_graph()
        self.executor.migrate(self.migrate_to)
        new_apps = self.executor.loader.project_state(self.migrate_to).apps
        RideParticipant = new_apps.get_model('coordinate', 'RideParticipant')

        # 1. Assert Host: CONFIRMED and disclose_ride_identity=True (fail-open host visibility)
        host_row = RideParticipant.objects.get(ride_id=self.ride.id, user_id=self.host.id)
        self.assertEqual(host_row.status, 'CONFIRMED')
        self.assertTrue(host_row.disclose_ride_identity)

        # 2. Consented passenger: CONFIRMED and inherits consent
        p1_row = RideParticipant.objects.get(ride_id=self.ride.id, user_id=self.passenger_consented.id)
        self.assertEqual(p1_row.status, 'CONFIRMED')
        self.assertTrue(p1_row.disclose_ride_identity)
        self.assertTrue(p1_row.share_contact_details)

        # 3. Unconsented passenger: CONFIRMED and disclose_ride_identity=False (fail-closed)
        p2_row = RideParticipant.objects.get(ride_id=self.ride.id, user_id=self.passenger_unconsented.id)
        self.assertEqual(p2_row.status, 'CONFIRMED')
        self.assertFalse(p2_row.disclose_ride_identity)
        self.assertFalse(p2_row.share_contact_details)

        # 4. Waitlisted user: WAITLISTED
        wl_row = RideParticipant.objects.get(ride_id=self.ride.id, user_id=self.waitlisted_user.id)
        self.assertEqual(wl_row.status, 'WAITLISTED')

        # 5. Pending user: PENDING and preserves note
        pend_row = RideParticipant.objects.get(ride_id=self.ride.id, user_id=self.pending_user.id)
        self.assertEqual(pend_row.status, 'PENDING')
        self.assertEqual(pend_row.note, 'Wait for me')

        # 6. Coexisting user (in participants and left_users): CONFIRMED wins
        coex_row = RideParticipant.objects.get(ride_id=self.ride.id, user_id=self.coexisting_user.id)
        self.assertEqual(coex_row.status, 'CONFIRMED')

        # 7. Kicked user: KICKED
        kick_row = RideParticipant.objects.get(ride_id=self.ride.id, user_id=self.kicked_user.id)
        self.assertEqual(kick_row.status, 'KICKED')
        self.assertTrue(kick_row.is_revoked)

    def tearDown(self):
        # Restore database to latest migration state
        self.executor = MigrationExecutor(connection)
        self.executor.loader.build_graph()
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())
        super().tearDown()
