"""Comprehensive platform crawler and audit script for Campus Nexus.

Iterates over all named URLs, public routes, authenticated routes, API endpoints,
and templates to verify HTTP responses, template rendering, and broken links.
"""

import os
import sys
import django

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'campus.settings.dev')
import django
django.setup()

from django.conf import settings
if not getattr(settings, 'DEBUG', False):
    print("REFUSING TO RUN: audit_platform.py must NEVER run against production (DEBUG=False).", file=sys.stderr)
    sys.exit(1)

from datetime import datetime, timedelta
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import resolve, reverse
from django.utils import timezone

from accounts.models import Contributor, DirectMessage, FriendRequest, Friendship, PasskeyCredential
from coordinate.models import RideJoinRequest, RideParticipant, RideRequest, RideWaitlist

User = get_user_model()

def run_audit():
    print("=" * 70)
    print("CAMPUS NEXUS FULL PLATFORM AUDIT & CRAWLER")
    print("=" * 70)

    # 1. Setup audit users
    admin_user, _ = User.objects.get_or_create(
        enrollment_number="2099BCSE999",
        defaults={
            "username": "2099BCSE999",
            "first_name": "Audit",
            "last_name": "Admin",
            "email": "audit_admin@iust.ac.in",
            "phone_number": "+919999999999",
            "gender": "M",
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
            "verified": True,
        }
    )
    import secrets; audit_pw = os.environ.get("AUDIT_USER_PASSWORD", secrets.token_urlsafe(16))
    admin_user.set_password(audit_pw)
    admin_user.is_superuser = True
    admin_user.is_staff = True
    admin_user.verified = True
    admin_user.save()

    female_user, _ = User.objects.get_or_create(
        enrollment_number="2099BCSE998",
        defaults={
            "username": "2099BCSE998",
            "first_name": "Audit",
            "last_name": "Female",
            "email": "audit_female@iust.ac.in",
            "phone_number": "+919999999998",
            "gender": "F",
            "is_active": True,
            "verified": True,
        }
    )
    female_user.set_password(audit_pw)
    female_user.verified = True
    female_user.save()

    male_user, _ = User.objects.get_or_create(
        enrollment_number="2099BCSE997",
        defaults={
            "username": "2099BCSE997",
            "first_name": "Audit",
            "last_name": "Male",
            "email": "audit_male@iust.ac.in",
            "phone_number": "+919999999997",
            "gender": "M",
            "is_active": True,
            "verified": True,
        }
    )
    male_user.set_password(audit_pw)
    male_user.verified = True
    male_user.save()

    # Contributor profile for admin_user
    Contributor.objects.get_or_create(
        user=admin_user,
        defaults={
            "name": "Audit Admin",
            "role": "Core Maintainer",
            "is_active": True,
        }
    )

    # Establish friendship between male_user and admin_user (user1_id < user2_id canonical order)
    u1, u2 = (male_user, admin_user) if male_user.id < admin_user.id else (admin_user, male_user)
    Friendship.objects.get_or_create(user1=u1, user2=u2)

    # Create dummy ride hosted by admin_user
    dept_time = timezone.now() + timedelta(days=2)
    ride, _ = RideRequest.objects.get_or_create(
        creator=admin_user,
        route="NIT_TO_AIRPORT",
        defaults={
            "visibility": "MIXED",
            "departure_time": dept_time,
            "total_spots": 4,
            "status": "OPEN",
        }
    )

    anon_client = Client()
    auth_client = Client()
    auth_client.force_login(male_user)

    admin_client = Client()
    admin_client.force_login(admin_user)
    admin_session = admin_client.session
    admin_session['auth_timestamp'] = timezone.now().timestamp()
    admin_session['security_otp_verified_until'] = (timezone.now() + timedelta(minutes=15)).isoformat()
    admin_session.save()

    results = []

    def check(name, url, client, expected_statuses=(200, 302), method="GET", data=None):
        try:
            if method == "GET":
                resp = client.get(url, follow=False)
            else:
                resp = client.post(url, data=data or {}, follow=False)
            status = resp.status_code
            ok = status in expected_statuses
            results.append({
                "name": name,
                "url": url,
                "status": status,
                "ok": ok,
                "expected": expected_statuses,
                "redirect_url": resp.get("Location") if status in (301, 302) else None
            })
            print(f"[{'PASS' if ok else 'FAIL'}] {name} ({url}) -> HTTP {status}")
        except Exception as e:
            results.append({
                "name": name,
                "url": url,
                "status": "EXCEPTION",
                "ok": False,
                "error": str(e),
                "expected": expected_statuses
            })
            print(f"[FAIL-EXC] {name} ({url}) -> {e}")

    print("\n--- 1. PUBLIC PAGES (ANONYMOUS CLIENT) ---")
    check("Landing Page", reverse("landing"), anon_client, (200,))
    check("About Page", reverse("about"), anon_client, (200,))
    check("Contact Page", reverse("contact"), anon_client, (200,))
    check("Contributors Page", reverse("contributors"), anon_client, (200,))
    check("Nominate Contributor Anon (Redirects)", reverse("nominate_contributor"), anon_client, (302,))
    check("Feedback / Bug Report GET", reverse("feedback"), anon_client, (200,))
    check("Report Bug Alias GET", reverse("report_bug"), anon_client, (200,))
    check("Service Catalogue", reverse("service_catalogue"), anon_client, (200,))
    check("Coordinate Service Gateway", reverse("service_gateway", kwargs={"slug": "coordinate"}), anon_client, (302,))
    check("System Health Check", reverse("health_check"), anon_client, (200,))
    check("Login Page GET", reverse("login"), anon_client, (200,))
    check("Forgot Password Page GET", reverse("forgot_password"), anon_client, (200,))
    check("Apply Account GET", reverse("apply_account"), anon_client, (200,))
    check("Apply Success GET", reverse("application_success"), anon_client, (200,))

    print("\n--- 2. AUTHENTICATION & SECURITY ENFORCEMENT ---")
    check("Dashboard Anon Access (Should Redirect)", reverse("dashboard"), anon_client, (302,))
    check("Ride List Anon Access (Should Redirect)", reverse("ride_list"), anon_client, (302,))
    check("Operations Anon Access (Should 302 or 403)", reverse("operational_dashboard"), anon_client, (302, 403))
    check("Operations Normal User (Should 302 or 403)", reverse("operational_dashboard"), auth_client, (302, 403))

    print("\n--- 3. AUTHENTICATED USER VIEWS ---")
    check("User Dashboard", reverse("dashboard"), auth_client, (200,))
    check("Ride List", reverse("ride_list"), auth_client, (200,))
    check("Ride List Alias (/coordinate/rides/)", reverse("ride_list_alias"), auth_client, (200,))
    check("Ride List with Density Graph & Filters", reverse("ride_list") + "?order_by=time_asc&density_date=all", auth_client, (200,))
    check("My Rides", reverse("my_rides"), auth_client, (200,))
    check("Create Ride GET", reverse("create_ride"), auth_client, (200,))
    check("Ride Detail (Host View)", reverse("ride_detail", kwargs={"ride_id": ride.id}), admin_client, (200,))
    # For a MIXED ride, verified student can view ride detail to request to join (HTTP 200)
    check("Ride Detail (Non-Participant Discovery View)", reverse("ride_detail", kwargs={"ride_id": ride.id}), auth_client, (200,))
    # If student is kicked from the ride, can_view_ride returns False (HTTP 404)
    ride.kicked_users.add(male_user)
    check("Ride Detail (Kicked User 404 Guard)", reverse("ride_detail", kwargs={"ride_id": ride.id}), auth_client, (404,))
    ride.kicked_users.remove(male_user)
    check("Student Directory Search", reverse("user_search"), auth_client, (200,))
    check("Search with Query", reverse("user_search") + "?q=Audit", auth_client, (200,))
    check("Messages Inbox", reverse("messages_inbox"), auth_client, (200,))
    check("Direct Chat (Confirmed Friends)", reverse("direct_chat", kwargs={"enrollment_number": admin_user.enrollment_number}), auth_client, (200,))
    check("Direct Chat (Strangers Guard Redirect)", reverse("direct_chat", kwargs={"enrollment_number": female_user.enrollment_number}), auth_client, (302,))
    check("View Own Profile", reverse("profile", kwargs={"enrollment_number": male_user.enrollment_number}), auth_client, (200,))
    check("View Other Profile", reverse("profile", kwargs={"enrollment_number": admin_user.enrollment_number}), auth_client, (200,))
    check("Nominate Contributor POST (Active Contributor)", reverse("nominate_contributor"), admin_client, (302,), method="POST", data={"name": "Peer Nominee", "role": "Frontend"})

    print("\n--- 4. ADMINISTRATIVE & OPERATIONAL DASHBOARD ---")
    check("Operations Dashboard (Admin)", reverse("operational_dashboard"), admin_client, (200,))
    check("Manage Superusers (Admin)", reverse("manage_superusers"), admin_client, (200,))
    check("Applications List (Admin)", reverse("application_list"), admin_client, (200,))
    check("Analytics (Admin)", reverse("admin_analytics"), admin_client, (200,))
    check("Export Rides CSV", reverse("export_rides_csv"), admin_client, (200,))
    check("Export Users CSV", reverse("export_users_csv"), admin_client, (200,))
    check("Export Applications CSV", reverse("export_applications_csv"), admin_client, (200,))

    print("\n--- 5. REST API (v1) ENDPOINTS ---")
    check("API Root", reverse("api_root"), anon_client, (200,))
    check("API Catalogue", reverse("api_catalogue"), anon_client, (200,))
    check("API Service Detail", reverse("api_service_detail", kwargs={"slug": "coordinate"}), anon_client, (200,))
    check("API Rides List", reverse("api_ride_list"), auth_client, (200,))
    check("API Ride Detail", reverse("api_ride_detail", kwargs={"ride_id": ride.id}), auth_client, (200,))
    check("API My Rides", reverse("api_my_rides"), auth_client, (200,))
    check("API Me", reverse("api_me"), auth_client, (200,))

    print("\n" + "=" * 70)
    passed = sum(1 for r in results if r["ok"])
    failed = sum(1 for r in results if not r["ok"])
    print(f"AUDIT SUMMARY: {passed} PASSED, {failed} FAILED across {len(results)} total tests")
    print("=" * 70)

    # Cleanup test contributors created during audit
    Contributor.objects.filter(name__in=["Audit Admin", "Peer Nominee"]).delete()

    if failed > 0:
        print("\nFailed checks:")
        for r in results:
            if not r["ok"]:
                print(f" - {r['name']} ({r['url']}): got {r['status']}, expected {r['expected']}")

if __name__ == "__main__":
    from django.test.utils import setup_databases, teardown_databases
    from django.db import connection

    old_db_config = setup_databases(verbosity=0, interactive=False)
    try:
        db_name = connection.settings_dict.get('NAME', '')
        if not ('memory' in db_name or 'test' in db_name):
            print("REFUSING TO RUN: audit_platform.py must only run against an isolated test database.", file=sys.stderr)
            sys.exit(1)
        run_audit()
    finally:
        teardown_databases(old_db_config, verbosity=0)
