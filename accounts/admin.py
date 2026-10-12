"""Admin registrations for the accounts app."""

from django.contrib import admin

from .models import AccountApplication, Friendship, FriendRequest, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['enrollment_number', 'get_full_name', 'gender', 'branch', 'degree', 'verified', 'rides_completed']
    list_filter = ['verified', 'gender', 'branch', 'degree']
    search_fields = ['enrollment_number', 'first_name', 'last_name', 'phone_number']
    readonly_fields = ['branch', 'degree', 'joining_year', 'roll_number']


@admin.register(AccountApplication)
class AccountApplicationAdmin(admin.ModelAdmin):
    list_display = ['application_number', 'enrollment_number', 'full_name', 'gender', 'approved', 'created_at']
    list_filter = ['approved', 'gender']
    search_fields = ['enrollment_number', 'full_name', 'application_number']


@admin.register(FriendRequest)
class FriendRequestAdmin(admin.ModelAdmin):
    list_display = ['sender', 'receiver', 'created_at']


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ['user1', 'user2', 'created_at']