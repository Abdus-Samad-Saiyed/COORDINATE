"""
User model and social models for COORDINATE.
"""

from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models


ENROLLMENT_VALIDATOR = RegexValidator(
    regex=r'^\d{4}[BMP][A-Z]{3}\d{3}$',
    message='Invalid enrollment number. Expected format: 2024BCSE001',
)

_DEGREE_MAP = {'B': 'Bachelors', 'M': 'Masters', 'P': 'PhD'}


class User(AbstractUser):
    """
    Custom user model where enrollment_number is the login credential.

    Enrollment format: 2024BCSE001
      [0:4]  → joining year   (2024)
      [4]    → degree code    (B/M/P)
      [5:8]  → branch code    (CSE, ECE, …)
      [8:11] → roll number    (001)
    """

    enrollment_number = models.CharField(
        max_length=11,
        unique=True,
        validators=[ENROLLMENT_VALIDATOR],
        db_index=True,
    )
    phone_number = models.CharField(max_length=15)

    # Auto-derived from enrollment_number on save
    branch = models.CharField(max_length=10, blank=True)
    degree = models.CharField(max_length=20, blank=True)
    joining_year = models.IntegerField(null=True, blank=True)
    roll_number = models.CharField(max_length=10, blank=True)

    GENDER_CHOICES = [('M', 'Male'), ('F', 'Female')]
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)

    verified = models.BooleanField(default=False)

    # Ride reliability stats
    rides_completed = models.IntegerField(default=0)
    on_time_count = models.IntegerField(default=0)
    late_count = models.IntegerField(default=0)
    no_show_count = models.IntegerField(default=0)
    behavior_reports = models.IntegerField(default=0)

    USERNAME_FIELD = 'enrollment_number'
    REQUIRED_FIELDS = ['username', 'gender', 'phone_number']

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        if self.enrollment_number:
            e = self.enrollment_number.upper()
            self.enrollment_number = e
            self.joining_year = int(e[:4])
            self.degree = _DEGREE_MAP.get(e[4], 'Unknown')
            self.branch = e[5:8]
            self.roll_number = e[8:]
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def on_time_percentage(self) -> float:
        total = self.on_time_count + self.late_count + self.no_show_count
        if total == 0:
            return 100.0
        return round((self.on_time_count / total) * 100, 1)

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.enrollment_number

    def __str__(self) -> str:
        return self.enrollment_number


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

class AccountApplication(models.Model):
    """
    A prospective student's application for a verified account.
    Admin reviews these and calls approve_application() to create the User.
    """

    enrollment_number = models.CharField(max_length=11, unique=True)
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=15)
    gender = models.CharField(max_length=1, choices=User.GENDER_CHOICES)
    password = models.CharField(max_length=255)          # stored hashed
    application_number = models.CharField(max_length=20, unique=True)
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Account Application'
        verbose_name_plural = 'Account Applications'

    def __str__(self) -> str:
        return f'{self.application_number} — {self.enrollment_number}'


# ---------------------------------------------------------------------------
# Social graph
# ---------------------------------------------------------------------------

class FriendRequest(models.Model):
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_friend_requests',
    )
    receiver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='received_friend_requests',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['sender', 'receiver'],
                name='unique_friend_request',
            ),
            models.CheckConstraint(
                check=~models.Q(sender=models.F('receiver')),
                name='no_self_friend_request',
            ),
        ]
        verbose_name = 'Friend Request'

    def __str__(self) -> str:
        return f'{self.sender} → {self.receiver}'


class Friendship(models.Model):
    user1 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='friendships_as_user1',
    )
    user2 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='friendships_as_user2',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user1', 'user2'],
                name='unique_friendship',
            ),
            models.CheckConstraint(
                check=~models.Q(user1=models.F('user2')),
                name='no_self_friendship',
            ),
        ]
        verbose_name = 'Friendship'

    def __str__(self) -> str:
        return f'{self.user1} ↔ {self.user2}'
