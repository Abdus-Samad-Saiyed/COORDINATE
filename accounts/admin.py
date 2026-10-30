"""Admin registrations for the accounts app."""

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    AccountApplication,
    AuditEvent,
    Contributor,
    DirectMessage,
    Friendship,
    FriendRequest,
    PasskeyCredential,
    PhoneOTP,
    PlatformFeedback,
    User,
    log_audit_event,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Custom UserAdmin inheriting from BaseUserAdmin to ensure proper
    password hashing, change forms, and admin user creation flows.
    """

    list_display = [
        'enrollment_number',
        'get_full_name',
        'gender',
        'branch',
        'degree',
        'verified',
        'rides_completed',
        'is_staff',
        'is_superuser',
    ]
    list_filter = ['verified', 'gender', 'branch', 'degree', 'is_staff', 'is_superuser']
    search_fields = ['enrollment_number', 'first_name', 'last_name', 'phone_number']
    ordering = ['enrollment_number']
    readonly_fields = ['branch', 'degree', 'joining_year', 'roll_number', 'last_login', 'date_joined']
    actions = []

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            ro.extend(['is_superuser', 'is_staff', 'user_permissions', 'groups'])
        else:
            ro.extend(['user_permissions'])
        return ro

    fieldsets = (
        (None, {'fields': ('enrollment_number', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'phone_number', 'gender')}),
        ('Academic info', {'fields': ('branch', 'degree', 'joining_year', 'roll_number')}),
        ('Permissions & Status', {
            'fields': ('verified', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Ride Statistics', {
            'fields': (
                'rides_completed',
                'on_time_count',
                'late_count',
                'no_show_count',
                'behavior_reports',
            ),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'enrollment_number',
                'phone_number',
                'gender',
                'password1',
                'password2',
                'is_staff',
                'is_superuser',
            ),
        }),
    )


@admin.register(AccountApplication)
class AccountApplicationAdmin(admin.ModelAdmin):
    list_display = ['application_number', 'enrollment_number', 'full_name', 'gender', 'approved', 'created_at']
    list_filter = ['approved', 'gender']
    search_fields = ['enrollment_number', 'full_name', 'application_number']
    readonly_fields = ['application_number', 'created_at']


@admin.register(FriendRequest)
class FriendRequestAdmin(admin.ModelAdmin):
    list_display = ['sender', 'receiver', 'created_at']
    search_fields = ['sender__enrollment_number', 'receiver__enrollment_number']


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ['user1', 'user2', 'created_at']
    search_fields = ['user1__enrollment_number', 'user2__enrollment_number']


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'event_type', 'actor_enrollment', 'target_id', 'description']
    list_filter = ['event_type', 'timestamp']
    search_fields = ['actor_enrollment', 'target_id', 'description']
    readonly_fields = ['timestamp', 'event_type', 'actor_enrollment', 'target_id', 'description']
    ordering = ['-timestamp']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PlatformFeedback)
class PlatformFeedbackAdmin(admin.ModelAdmin):
    list_display = ['title', 'feedback_type', 'user', 'submitter_name', 'status', 'created_at']
    list_filter = ['feedback_type', 'status', 'created_at']
    search_fields = ['title', 'description', 'submitter_name', 'user__enrollment_number']
    readonly_fields = ['created_at']


@admin.register(DirectMessage)
class DirectMessageAdmin(admin.ModelAdmin):
    list_display = ['sender', 'recipient', 'content', 'is_read', 'created_at']
    list_filter = ['is_read', 'created_at']
    search_fields = ['sender__enrollment_number', 'recipient__enrollment_number', 'content']
    readonly_fields = ['created_at']


@admin.register(PhoneOTP)
class PhoneOTPAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone_number', 'attempts_left', 'is_used', 'created_at', 'expires_at']
    list_filter = ['is_used', 'created_at']
    search_fields = ['user__enrollment_number', 'phone_number']
    readonly_fields = ['otp_hash', 'created_at']


@admin.register(PasskeyCredential)
class PasskeyCredentialAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'sign_count', 'created_at', 'last_used_at']
    search_fields = ['user__enrollment_number', 'name', 'credential_id']
    readonly_fields = ['credential_id', 'public_key', 'created_at']


@admin.register(Contributor)
class ContributorAdmin(admin.ModelAdmin):
    list_display = ['name', 'role', 'enrollment_number', 'nominated_by', 'is_active', 'created_at']
    list_filter = ['is_active', 'role']
    search_fields = ['name', 'enrollment_number', 'role', 'bio']
    readonly_fields = ['created_at']