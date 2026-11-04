from django.core.management.base import BaseCommand
from coordinate.models import ParticipantStatus, RideConsent, RideJoinRequest, RideParticipant, RideRequest, RideWaitlist


class Command(BaseCommand):
    help = "Verify that all legacy ride participation rows are cleanly accounted for in RideParticipant."

    def handle(self, *args, **options):
        self.stdout.write("Auditing ride participation state backfill...")
        errors = 0
        total_unified = RideParticipant.all_rows.count()
        confirmed_unified = RideParticipant.objects.count()

        self.stdout.write(f"  Total Unified Rows    : {total_unified}")
        self.stdout.write(f"  Confirmed Active Rows : {confirmed_unified}")

        # 1. Check legacy RideParticipant
        for rp in RideParticipant.all_rows.filter(status=ParticipantStatus.CONFIRMED):
            if not RideRequest.objects.filter(id=rp.ride_id).exists():
                self.stderr.write(f"  [ERROR] Orphaned RideParticipant #{rp.id} references non-existent ride #{rp.ride_id}")
                errors += 1

        # 2. Check waitlist accounting
        for wl in RideWaitlist.objects.all():
            row = RideParticipant.all_rows.filter(ride_id=wl.ride_id, user_id=wl.user_id).first()
            if not row:
                self.stderr.write(f"  [ERROR] RideWaitlist row ({wl.ride_id}, {wl.user_id}) missing in RideParticipant!")
                errors += 1
            elif row.status not in (ParticipantStatus.WAITLISTED, ParticipantStatus.CONFIRMED):
                self.stderr.write(f"  [WARN] RideWaitlist ({wl.ride_id}, {wl.user_id}) mapped to lower status: {row.status}")

        # 3. Check join requests
        for jr in RideJoinRequest.objects.exclude(status='APPROVED'):
            row = RideParticipant.all_rows.filter(ride_id=jr.ride_id, user_id=jr.user_id).first()
            if not row:
                self.stderr.write(f"  [ERROR] Join request #{jr.id} ({jr.ride_id}, {jr.user_id}) missing in RideParticipant!")
                errors += 1

        # 4. Check consent consistency
        for c in RideConsent.objects.all():
            row = RideParticipant.all_rows.filter(ride_id=c.ride_id, user_id=c.user_id).first()
            if row:
                if row.disclose_ride_identity != c.disclose_ride_identity:
                    self.stderr.write(f"  [ERROR] Consent mismatch for ({c.ride_id}, {c.user_id}): identity disclosure differs!")
                    errors += 1

        if errors == 0:
            self.stdout.write(self.style.SUCCESS("[OK] Backfill verification passed with 0 discrepancies!"))
        else:
            self.stdout.write(self.style.ERROR(f"[FAIL] Backfill verification found {errors} issues."))
