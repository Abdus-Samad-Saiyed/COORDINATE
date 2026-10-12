from django.contrib import admin

from .models import (
    RideRequest,
    RideParticipant,
    RideMessage,
    RideReview
)


admin.site.register(RideRequest)
admin.site.register(RideParticipant)
admin.site.register(RideMessage)
admin.site.register(RideReview)
