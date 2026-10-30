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
    actions = ['promote_to_superuser', 'revoke_superuser']

    @admin.action(description='Promote selected users to Superuser')
    def promote_to_superuser(self, request, queryset):
        actor_enrollment = getattr(request.user, 'enrollment_number', 'admin')
        promoted = 0
        for u in queryset:
            if not u.is_superuser:
                u.is_superuser = True
                u.is_staff = True
                u.save(update_fields=['is_superuser', 'is_staff'])
                log_audit_event(
                    event_type='SUPERUSER_PROMOTED',
                    actor_enrollment=actor_enrollment,
                    description=f'Promoted {u.enrollment_number} ({u.get_full_name()}) to superuser via Django admin',
                    target_id=u.enrollment_number,
                )
                promoted += 1
        self.message_user(request, f'Promoted {promoted} user(s) to superuser.', level=messages.SUCCESS)

    @admin.action(description='Revoke Superuser privileges from selected users')
    def revoke_superuser(self, request, queryset):
        actor_enrollment = getattr(request.user, 'enrollment_number', 'admin')
        active_superusers = User.objects.filter(is_superuser=True, is_active=True).count()
        revoked = 0

        for u in queryset:
            if u.is_superuser:
                if active_superusers <= 1 and u.is_active:
                    self.message_user(
                        request,
                        f'Cannot revoke {u.enrollment_number}: at least one active superuser must remain to prevent lockout.',
                        level=messages.ERROR,
                    )
                    continue
                u.is_superuser = False
                u.save(update_fields=['is_superuser'])
                active_superusers -= 1
                log_audit_event(
                    event_type='SUPERUSER_REVOKED',
                    actor_enrollment=actor_enrollment,
                    description=f'Revoked superuser from {u.enrollment_number} ({u.get_full_name()}) via Django admin',
                    target_id=u.enrollment_number,
                )
                revoked += 1
        if revoked:
            self.message_user(request, f'Revoked superuser privileges from {revoked} user(s).', level=messages.SUCCESS)

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