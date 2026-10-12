from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from accounts.models import User


class RideRequest(models.Model):

    ROUTE_CHOICES = [

        (
            'NIT_TO_AIRPORT',
            'NIT Srinagar → Airport'
        ),

        (
            'AIRPORT_TO_NIT',
            'Airport → NIT Srinagar'
        ),

        (
            'NIT_TO_STATION',
            'NIT Srinagar → Railway Station'
        ),

        (
            'STATION_TO_NIT',
            'Railway Station → NIT Srinagar'
        ),

        (
            'CUSTOM',
            'Custom Route'
        ),
    ]

    VISIBILITY_CHOICES = [

        ('MIXED', 'Mixed'),

        ('BOYS', 'Boys Only'),

        ('GIRLS', 'Girls Only'),

        ('FRIENDS', 'Friends Only'),
    ]

    STATUS_CHOICES = [

        ('OPEN', 'Open'),

        ('FULL', 'Full'),

        ('COMPLETED', 'Completed'),
    ]

    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_rides'
    )

    route = models.CharField(
        max_length=30,
        choices=ROUTE_CHOICES
    )

    custom_from_location = models.CharField(
        max_length=255,
        blank=True
    )

    custom_to_location = models.CharField(
        max_length=255,
        blank=True
    )

    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES
    )

    departure_time = models.DateTimeField()

    total_spots = models.IntegerField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='OPEN'
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def participant_count(self):

        if not self.pk:

            return 0

        return RideParticipant.objects.filter(
            ride=self
        ).count()

    def spots_remaining(self):

        return (
            self.total_spots -
            self.participant_count()
        )

    def is_full(self):

        return (
            self.participant_count()
            >= self.total_spots
        )

    def route_display(self):

        if (
            self.route == 'CUSTOM' and
            self.custom_from_location and
            self.custom_to_location
        ):

            return (
                f"{self.custom_from_location} -> "
                f"{self.custom_to_location}"
            )

        return self.get_route_display()

    def sync_status(self, commit=True):

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

    def __str__(self):

        return (
            f"{self.creator} - "
            f"{self.route}"
        )


class RideParticipant(models.Model):

    ride = models.ForeignKey(
        RideRequest,
        on_delete=models.CASCADE
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    joined_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        constraints = [
            models.UniqueConstraint(
                fields=['ride', 'user'],
                name='unique_ride_participant'
            )
        ]

    def __str__(self):

        return (
            f"{self.user} in {self.ride}"
        )


class RideReview(models.Model):

    RATING_CHOICES = [

        (1, '1'),
        (2, '2'),
        (3, '3'),
        (4, '4'),
        (5, '5'),
    ]

    ride = models.ForeignKey(
        RideRequest,
        on_delete=models.CASCADE
    )

    reviewer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='given_reviews'
    )

    reviewed_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='received_reviews'
    )

    rating = models.IntegerField(
        choices=RATING_CHOICES
    )

    complaint = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        constraints = [
            models.UniqueConstraint(
                fields=['ride', 'reviewer', 'reviewed_user'],
                name='unique_ride_review'
            )
        ]

    def __str__(self):

        return (
            f"{self.reviewer} -> "
            f"{self.reviewed_user}"
        )


class RideMessage(models.Model):

    ride = models.ForeignKey(
        RideRequest,
        on_delete=models.CASCADE,
        related_name='messages'
    )

    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    content = models.TextField(
        max_length=1000
    )

    created_at = models.DateTimeField(
        default=timezone.now
    )

    def clean(self):

        if not self.content or not self.content.strip():

            raise ValidationError(
                {'content': 'Message cannot be empty.'}
            )

        self.content = self.content.strip()

    def __str__(self):

        return (
            f"{self.author} in ride "
            f"{self.ride_id}"
        )
