"""
Ride coordination models for COORDINATE.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from accounts.models import User


class RideRequest(models.Model):
    """A shared cab ride that students can join."""

    ROUTE_CHOICES = [
        ('NIT_TO_AIRPORT',  'NIT Srinagar → Airport'),
        ('AIRPORT_TO_NIT',  'Airport → NIT Srinagar'),
        ('NIT_TO_STATION',  'NIT Srinagar → Railway Station'),
        ('STATION_TO_NIT',  'Railway Station → NIT Srinagar'),
        ('CUSTOM',          'Custom Route'),
    ]

    VISIBILITY_CHOICES = [
        ('MIXED',   'Mixed'),
        ('BOYS',    'Boys Only'),
        ('GIRLS',   'Girls Only'),
        ('FRIENDS', 'Friends Only'),
    ]

    STATUS_CHOICES = [
        ('OPEN',      'Open'),
        ('FULL',      'Full'),
        ('COMPLETED', 'Completed'),
    ]

    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_rides',
    )
    route = models.CharField(max_length=30, choices=ROUTE_CHOICES)
    custom_from_location = models.CharField(max_length=255, blank=True)
    custom_to_location = models.CharField(max_length=255, blank=True)
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES)
    departure_time = models.DateTimeField()
    total_spots = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Ride Request'
        verbose_name_plural = 'Ride Requests'

    # ------------------------------------------------------------------
    # Computed helpers
    # ------------------------------------------------------------------

    @property
    def route_display(self) -> str:
        """Human-readable route string, handling custom routes."""
        if self.route == 'CUSTOM' and self.custom_from_location and self.custom_to_location:
            return f'{self.custom_from_location} → {self.custom_to_location}'
        return self.get_route_display()

    def participant_count(self) -> int:
        if not self.pk:
            return 0
        return self.participants.count()

    def spots_remaining(self) -> int:
        return self.total_spots - self.participant_count()

    def is_full(self) -> bool:
        return self.participant_count() >= self.total_spots

    # ------------------------------------------------------------------
    # Status management
    # ------------------------------------------------------------------

    def sync_status(self, commit: bool = True) -> None:
        """Recalculate OPEN/FULL status based on current headcount."""
        if self.status == 'COMPLETED':
            return
        self.status = 'FULL' if self.is_full() else 'OPEN'
        if commit and self.pk:
            self.save(update_fields=['status'])

    def save(self, *args, **kwargs):
        if not self.pk:
            if self.status != 'COMPLETED':
                self.status = 'OPEN'
        elif self.status != 'COMPLETED':
            self.status = 'FULL' if self.is_full() else 'OPEN'
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'{self.creator} — {self.get_route_display()}'


class RideParticipant(models.Model):
    """Membership table: which users are in which ride."""

    ride = models.ForeignKey(
        RideRequest,
        on_delete=models.CASCADE,
        related_name='participants',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='ride_participations',
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['ride', 'user'],
                name='unique_ride_participant',
            )
        ]
        verbose_name = 'Ride Participant'

    def __str__(self) -> str:
        return f'{self.user} in {self.ride}'


class RideReview(models.Model):
    """Post-ride peer review submitted after a ride is completed."""

    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    ride = models.ForeignKey(RideRequest, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='given_reviews')
    reviewed_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_reviews')
    rating = models.IntegerField(choices=RATING_CHOICES)
    complaint = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['ride', 'reviewer', 'reviewed_user'],
                name='unique_ride_review',
            )
        ]
        verbose_name = 'Ride Review'

    def __str__(self) -> str:
        return f'{self.reviewer} → {self.reviewed_user} (ride {self.ride_id})'


class RideMessage(models.Model):
    """An in-ride chat message."""

    ride = models.ForeignKey(
        RideRequest,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ride_messages')
    content = models.TextField(max_length=1000)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Ride Message'

    def clean(self):
        if not self.content or not self.content.strip():
            raise ValidationError({'content': 'Message cannot be empty.'})
        self.content = self.content.strip()

    def __str__(self) -> str:
        return f'{self.author} in ride {self.ride_id}'
