"""Admin registrations for the coordinate app."""

from django.contrib import admin

from .models import (
    RideIncidentReport,
    RideJoinRequest,
    RideMessage,
    RideParticipant,
    RideRequest,
    RideReview,
    RideWaitlist,
)


@admin.register(RideRequest)
class RideRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'creator', 'route', 'visibility', 'departure_time', 'total_spots', 'status', 'created_at']
    list_filter = ['status', 'route', 'visibility']
    search_fields = ['creator__enrollment_number', 'custom_from_location', 'custom_to_location']
    readonly_fields = ['created_at']


@admin.register(RideJoinRequest)
class RideJoinRequestAdmin(admin.ModelAdmin):
    list_display = ['ride', 'user', 'status', 'created_at', 'reviewed_at']
    list_filter = ['status']
    search_fields = ['user__enrollment_number', 'ride__id']


@admin.register(RideParticipant)
class RideParticipantAdmin(admin.ModelAdmin):
    list_display = ['ride', 'user', 'joined_at']
    search_fields = ['user__enrollment_number']


@admin.register(RideWaitlist)
class RideWaitlistAdmin(admin.ModelAdmin):
    list_display = ['ride', 'user', 'joined_at']
    search_fields = ['user__enrollment_number']


@admin.register(RideReview)
class RideReviewAdmin(admin.ModelAdmin):
    list_display = ['ride', 'reviewer', 'reviewed_user', 'rating', 'grievance', 'created_at']
    list_filter = ['rating', 'grievance']


@admin.register(RideMessage)
class RideMessageAdmin(admin.ModelAdmin):
    list_display = ['ride', 'author', 'created_at']
    search_fields = ['author__enrollment_number', 'content']


@admin.register(RideIncidentReport)
class RideIncidentReportAdmin(admin.ModelAdmin):
    list_display = ['reference_id', 'ride', 'reporter', 'reported_user', 'category', 'status', 'created_at']
    list_filter = ['category', 'status', 'escalated_to_institute']
    search_fields = ['reference_id', 'reporter__enrollment_number', 'reported_user__enrollment_number', 'statement']
    readonly_fields = ['reference_id', 'created_at']


