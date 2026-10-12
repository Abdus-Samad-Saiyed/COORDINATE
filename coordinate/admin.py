"""Admin registrations for the coordinate app."""

from django.contrib import admin

from .models import RideMessage, RideParticipant, RideRequest, RideReview


@admin.register(RideRequest)
class RideRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'creator', 'route', 'visibility', 'departure_time', 'total_spots', 'status', 'created_at']
    list_filter = ['status', 'route', 'visibility']
    search_fields = ['creator__enrollment_number', 'custom_from_location', 'custom_to_location']
    readonly_fields = ['created_at']


@admin.register(RideParticipant)
class RideParticipantAdmin(admin.ModelAdmin):
    list_display = ['ride', 'user', 'joined_at']
    search_fields = ['user__enrollment_number']


@admin.register(RideReview)
class RideReviewAdmin(admin.ModelAdmin):
    list_display = ['ride', 'reviewer', 'reviewed_user', 'rating', 'created_at']
    list_filter = ['rating']


@admin.register(RideMessage)
class RideMessageAdmin(admin.ModelAdmin):
    list_display = ['ride', 'author', 'created_at']
    search_fields = ['author__enrollment_number', 'content']
