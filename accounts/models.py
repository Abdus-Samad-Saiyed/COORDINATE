from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import RegexValidator


class User(AbstractUser):

    enrollment_number = models.CharField(
        max_length=11,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^\d{4}[BMP][A-Z]{3}\d{3}$',
                message='Invalid enrollment number format'
            )
        ]
    )

    phone_number = models.CharField(
        max_length=15
    )

    branch = models.CharField(
        max_length=10,
        blank=True
    )

    degree = models.CharField(
        max_length=20,
        blank=True
    )

    joining_year = models.IntegerField(
        null=True,
        blank=True
    )

    roll_number = models.CharField(
        max_length=10,
        blank=True
    )

    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
    ]

    gender = models.CharField(
        max_length=1,
        choices=GENDER_CHOICES,
        blank=True
    )

    verified = models.BooleanField(
        default=False
    )

    rides_completed = models.IntegerField(
        default=0
    )

    on_time_count = models.IntegerField(
        default=0
    )

    late_count = models.IntegerField(
        default=0
    )

    no_show_count = models.IntegerField(
        default=0
    )

    behavior_reports = models.IntegerField(
        default=0
    )

    USERNAME_FIELD = 'enrollment_number'

    REQUIRED_FIELDS = [
        'username',
        'gender',
        'phone_number'
    ]

    def save(self, *args, **kwargs):

        if self.enrollment_number:

            enrollment = (
                self.enrollment_number.upper()
            )

            self.enrollment_number = enrollment

            self.joining_year = int(
                enrollment[:4]
            )

            degree_code = enrollment[4]

            branch_code = enrollment[5:8]

            self.roll_number = enrollment[8:]

            degree_map = {
                'B': 'Bachelors',
                'M': 'Masters',
                'P': 'PhD',
            }

            self.degree = degree_map.get(
                degree_code,
                'Unknown'
            )

            self.branch = branch_code

        super().save(*args, **kwargs)

    def on_time_percentage(self):

        total = (
            self.on_time_count +
            self.late_count +
            self.no_show_count
        )

        if total == 0:

            return 100

        return round(
            (self.on_time_count / total) * 100,
            1
        )

    def __str__(self):

        return self.enrollment_number


class AccountApplication(models.Model):

    enrollment_number = models.CharField(
        max_length=11,
        unique=True
    )

    full_name = models.CharField(
        max_length=255
    )

    phone_number = models.CharField(
        max_length=15
    )

    gender = models.CharField(
        max_length=1,
        choices=User.GENDER_CHOICES
    )

    password = models.CharField(
        max_length=255
    )

    application_number = models.CharField(
        max_length=20,
        unique=True
    )

    approved = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return self.application_number


class FriendRequest(models.Model):

    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_requests'
    )

    receiver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='received_requests'
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        constraints = [
            models.UniqueConstraint(
                fields=['sender', 'receiver'],
                name='unique_friend_request'
            ),
            models.CheckConstraint(
                condition=~models.Q(sender=models.F('receiver')),
                name='prevent_self_friend_request'
            )
        ]


class Friendship(models.Model):

    user1 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='friendship_1'
    )

    user2 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='friendship_2'
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        constraints = [
            models.UniqueConstraint(
                fields=['user1', 'user2'],
                name='unique_friendship_pair'
            ),
            models.CheckConstraint(
                condition=~models.Q(user1=models.F('user2')),
                name='prevent_self_friendship'
            )
        ]
