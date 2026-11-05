"""Tests for client request identity console logging (enrollment number, name, and IP address)."""

import logging
from unittest.mock import MagicMock, patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase

from accounts.client_logger import (
    ClientLoggingASGIWrapper,
    pop_client_request,
    resolve_client_display,
    seed_client_request,
    update_or_record_client_request,
)
from accounts.management.commands.runserver import Command
from accounts.middleware import ClientIdentityLoggingMiddleware

User = get_user_model()


class ClientLoggerRegistryTests(TestCase):
    """Test registry functions for client metadata tracking."""

    def test_resolve_client_display_local(self):
        """Local loopback addresses retain client key with port."""
        res = resolve_client_display("127.0.0.1:65521", "127.0.0.1")
        self.assertEqual(res, "127.0.0.1:65521")

    def test_resolve_client_display_proxy_with_port(self):
        """Proxy/Cloudflare real IP replaces loopback host while preserving port."""
        res = resolve_client_display("127.0.0.1:37548", "203.0.113.195")
        self.assertEqual(res, "203.0.113.195:37548")

    def test_resolve_client_display_none_or_missing(self):
        """Handles missing client key gracefully."""
        self.assertEqual(resolve_client_display(None, "198.51.100.1"), "198.51.100.1")
        self.assertEqual(resolve_client_display(None, None), "127.0.0.1")

    def test_seed_and_pop_client_request_defaults(self):
        """Seeded request returns defaults N.A. for enrollment and name."""
        client_key = "192.168.1.10:44111"
        seed_client_request(client_key, real_client=client_key)
        item = pop_client_request(client_key)
        self.assertEqual(item["enrollment"], "N.A.")
        self.assertEqual(item["name"], "N.A.")
        self.assertEqual(item["real_client"], client_key)

    def test_update_client_request(self):
        """Updating seeded request sets authenticated user metadata."""
        client_key = "192.168.1.10:44112"
        seed_client_request(client_key)
        update_or_record_client_request(
            client_key,
            enrollment="2024BCSE065",
            name="Abdus Samad Saiyed",
            real_client="203.0.113.50:44112",
        )
        item = pop_client_request(client_key)
        self.assertEqual(item["enrollment"], "2024BCSE065")
        self.assertEqual(item["name"], "Abdus Samad Saiyed")
        self.assertEqual(item["real_client"], "203.0.113.50:44112")

    def test_pop_nonexistent_returns_defaults(self):
        """Popping a client key with no records returns safe defaults."""
        item = pop_client_request("10.0.0.99:9999")
        self.assertEqual(item["enrollment"], "N.A.")
        self.assertEqual(item["name"], "N.A.")
        self.assertEqual(item["real_client"], "10.0.0.99:9999")


class ClientIdentityLoggingMiddlewareTests(TestCase):
    """Test middleware identity extraction for both anonymous and authenticated sessions."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="2024BCSE065",
            enrollment_number="2024BCSE065",
            first_name="Abdus Samad",
            last_name="Saiyed",
            email="2024bcse065@nitsri.ac.in",
            password="TestPassword123!",
            is_active=True,
            verified=True,
        )

    def test_unauthenticated_request_records_na(self):
        """Unauthenticated requests record N.A. for enrollment and name."""
        request = self.factory.get("/")
        request.user = AnonymousUser()
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["REMOTE_PORT"] = 23986

        middleware = ClientIdentityLoggingMiddleware(lambda req: MagicMock(status_code=200))
        middleware(request)

        item = pop_client_request("127.0.0.1:23986")
        self.assertEqual(item["enrollment"], "N.A.")
        self.assertEqual(item["name"], "N.A.")
        self.assertEqual(item["real_client"], "127.0.0.1:23986")

    def test_authenticated_request_records_user_info(self):
        """Authenticated requests record user's enrollment number and full name."""
        request = self.factory.get("/rides/")
        request.user = self.user
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["REMOTE_PORT"] = 65521

        middleware = ClientIdentityLoggingMiddleware(lambda req: MagicMock(status_code=200))
        middleware(request)

        item = pop_client_request("127.0.0.1:65521")
        self.assertEqual(item["enrollment"], "2024BCSE065")
        self.assertEqual(item["name"], "Abdus Samad Saiyed")
        self.assertEqual(item["real_client"], "127.0.0.1:65521")

    def test_cloudflare_header_extracts_real_ip(self):
        """CF-Connecting-IP header sets real client IP on recorded request."""
        request = self.factory.get("/profile/2024BCSE065/")
        request.user = self.user
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["REMOTE_PORT"] = 37548
        request.META["HTTP_CF_CONNECTING_IP"] = "103.21.244.2"

        middleware = ClientIdentityLoggingMiddleware(lambda req: MagicMock(status_code=200))
        middleware(request)

        item = pop_client_request("127.0.0.1:37548")
        self.assertEqual(item["enrollment"], "2024BCSE065")
        self.assertEqual(item["name"], "Abdus Samad Saiyed")
        self.assertEqual(item["real_client"], "103.21.244.2:37548")

    def test_bearer_token_resolves_authenticated_user(self):
        """Bearer token in Authorization header resolves authenticated user for API calls."""
        session = SessionStore()
        session["_auth_user_id"] = str(self.user.pk)
        session.create()

        request = self.factory.get("/api/v1/rides/")
        request.user = AnonymousUser()
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["REMOTE_PORT"] = 55123
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {session.session_key}"

        middleware = ClientIdentityLoggingMiddleware(lambda req: MagicMock(status_code=200))
        middleware(request)

        item = pop_client_request("127.0.0.1:55123")
        self.assertEqual(item["enrollment"], "2024BCSE065")
        self.assertEqual(item["name"], "Abdus Samad Saiyed")


class RunserverCommandLogActionTests(TestCase):
    """Test Command.log_action formatting of HTTP request output lines."""

    def setUp(self):
        self.cmd = Command()

    def test_log_action_unauthenticated_format(self):
        """Unauthenticated request logs with N.A. for enrollment and name."""
        details = {
            "method": "GET",
            "path": "/",
            "status": 200,
            "time_taken": 0.00,
            "client": "127.0.0.1:23986",
        }
        with self.assertLogs("django.channels.server", level="INFO") as cm:
            self.cmd.log_action("http", "complete", details)
            self.assertTrue(any(
                "HTTP GET / 200 [0.00, 127.0.0.1:23986, N.A., N.A.]" in msg
                for msg in cm.output
            ))

    def test_log_action_authenticated_format(self):
        """Authenticated request logs with enrollment number and name."""
        client_key = "127.0.0.1:37548"
        update_or_record_client_request(
            client_key,
            enrollment="2024BCSE065",
            name="Abdus Samad Saiyed",
            real_client=client_key,
        )
        details = {
            "method": "POST",
            "path": "/profile/2024BCSE065/",
            "status": 302,
            "time_taken": 0.02,
            "client": client_key,
        }
        with self.assertLogs("django.channels.server", level="INFO") as cm:
            self.cmd.log_action("http", "complete", details)
            self.assertTrue(any(
                "HTTP POST /profile/2024BCSE065/ 302 [0.02, 127.0.0.1:37548, 2024BCSE065, Abdus Samad Saiyed]" in msg
                for msg in cm.output
            ))

    def test_log_action_bad_request_warning(self):
        """400 Bad Request logs via warning level with formatted client details."""
        client_key = "127.0.0.1:37548"
        update_or_record_client_request(
            client_key,
            enrollment="2024BCSE065",
            name="Abdus Samad Saiyed",
            real_client=client_key,
        )
        details = {
            "method": "POST",
            "path": "/auth/passkey/register/verify/",
            "status": 400,
            "time_taken": 0.01,
            "client": client_key,
        }
        with self.assertLogs("django.channels.server", level="WARNING") as cm:
            self.cmd.log_action("http", "complete", details)
            self.assertTrue(any(
                "HTTP POST /auth/passkey/register/verify/ 400 [0.01, 127.0.0.1:37548, 2024BCSE065, Abdus Samad Saiyed]" in msg
                for msg in cm.output
            ))

    def test_websocket_log_action(self):
        """WebSocket connection logs formatted with client, enrollment, and name."""
        client_key = "127.0.0.1:44444"
        update_or_record_client_request(
            client_key,
            enrollment="2024BCSE065",
            name="Abdus Samad Saiyed",
            real_client=client_key,
        )
        details = {
            "path": "/ws/ride/1/",
            "client": client_key,
        }
        with self.assertLogs("django.channels.server", level="INFO") as cm:
            self.cmd.log_action("websocket", "connected", details)
            self.assertTrue(any(
                "WebSocket CONNECT /ws/ride/1/ [127.0.0.1:44444, 2024BCSE065, Abdus Samad Saiyed]" in msg
                for msg in cm.output
            ))


class ClientLoggingASGIWrapperTests(TestCase):
    """Test ASGI application wrapper metadata interception."""

    async def test_asgi_wrapper_seeds_static_metadata(self):
        """ASGI wrapper pre-seeds metadata for static or fast requests."""
        called = False

        async def inner_app(scope, receive, send):
            nonlocal called
            called = True

        wrapper = ClientLoggingASGIWrapper(inner_app)
        scope = {
            "type": "http",
            "client": ("127.0.0.1", 23986),
            "headers": [],
        }
        await wrapper(scope, None, None)
        self.assertTrue(called)

        item = pop_client_request("127.0.0.1:23986")
        self.assertEqual(item["enrollment"], "N.A.")
        self.assertEqual(item["name"], "N.A.")
        self.assertEqual(item["real_client"], "127.0.0.1:23986")

    async def test_asgi_wrapper_seeds_cloudflare_ip(self):
        """ASGI wrapper extracts cf-connecting-ip from raw scope headers."""
        async def inner_app(scope, receive, send):
            pass

        wrapper = ClientLoggingASGIWrapper(inner_app)
        scope = {
            "type": "http",
            "client": ("127.0.0.1", 37548),
            "headers": [
                (b"cf-connecting-ip", b"103.21.244.2"),
            ],
        }
        await wrapper(scope, None, None)

        item = pop_client_request("127.0.0.1:37548")
        self.assertEqual(item["real_client"], "103.21.244.2:37548")

