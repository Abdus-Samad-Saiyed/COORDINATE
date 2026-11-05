# Campus Nexus — System Architecture & Data Model

---

## 1. Architectural Topology

Campus Nexus is built on a hybrid **WSGI / ASGI** infrastructure powered by **Django 5** and **Django Channels 4**. This enables synchronous relational transactions (account provisioning, ride matching, review submissions) alongside persistent asynchronous WebSockets connections for real-time peer chat and coordination alerts.

```
                              [ HTTPS / WSS Clients ]
                                         |
                                         v
                            [ NGINX Reverse Proxy ]
                          (SSL, HTTP/2, Static Cache)
                                         |
                  +----------------------+----------------------+
                  |                                             |
                  v                                             v
       [ HTTP / REST Traffic ]                       [ WebSocket Traffic ]
                  |                                             |
                  v                                             v
         [ Django WSGI / ASGI ]                       [ Channels Protocol Router ]
                  |                                             |
                  |                                 +-----------+-----------+
                  |                                 |                       |
                  |                                 v                       v
                  |                         [ Direct Chat ]         [ Ride Group Chat ]
                  |                       (user_<enrollment>)          (ride_<id>)
                  |                                 |                       |
                  +---------------------------------+-----------------------+
                                         |
                         +---------------+---------------+
                         |                               |
                         v                               v
             [ PostgreSQL / SQLite ]         [ Redis Channel Layers ]
             (Relational Data Store)        (IPC, WebSockets, Cache)
```

---

## 2. Core Subsystems & Components

### 2.1 Umbrella Service Registry (`campus.services`)
Rather than maintaining siloed applications, Campus Nexus uses a centralized **Service Registry**:
- Services declare their identifier, slug, display metadata, launch routing, and activation state (`is_active: bool`).
- Active services route to their respective module (e.g. `/coordinate/rides/`).
- In-development services route through a server-authoritative gateway (`service_gateway_view`), which renders a diagnostic preview template (`service_unavailable.html`) with HTTP 403 Forbidden, preventing unauthorized direct URL bypass.

### 2.2 Telemetry & Real-Time Traffic Observability (`campus.telemetry`)
`TrafficTelemetryMiddleware` intercepts all inbound HTTP requests to record:
- Total request volume and rolling average latency (in milliseconds).
- Peak requests-per-second (RPS) tracking.
- System uptime and operational health state served at `/health/` for cluster load balancers.

---

## 3. Database Schema & Data Models

### 3.1 Identity & Governance Domain (`accounts` app)

| Model | Primary Purpose | Key Fields |
| :--- | :--- | :--- |
| **`User`** | Central identity entity based on `AbstractUser`. | `enrollment_number` (Unique, Indexed), `phone_number`, `email`, `branch`, `degree`, `joining_year`, `roll_number`, `verified`, `two_factor_enabled`, `current_session_key`, `is_deleted`. |
| **`AccountApplication`** | Queue of pending student registrations requiring verification. | `enrollment_number`, `full_name`, `email`, `phone_number`, `phone_verified`, `application_number`, `approved`. |
| **`PhoneOTP`** | Single-use 6-digit cryptographic verification codes. | `phone_number`, `email`, `otp_hash`, `purpose` (`SIGNUP`, `2FA`, `SECURITY_CHANGE`, `PASSWORD_RESET`), `attempts`, `expires_at`, `is_used`. |
| **`PasskeyCredential`** | FIDO2 / WebAuthn registered hardware keys. | `user`, `credential_id`, `public_key`, `sign_count`, `transports`, `name`. |
| **`PhysicalVerificationRequest`** | In-person offline desk verification tickets. | `user`, `contact_phone`, `reason`, `status` (`PENDING`, `VERIFIED`, `REJECTED`), `verified_by`, `resolution_notes`. |
| **`Friendship`** | Canonical bidirectional social connections between students. | `user1` (id < user2), `user2`, `created_at`. |
| **`FriendRequest`** | Pending connection invitations. | `sender`, `receiver`, `status`, `created_at`. |
| **`DirectMessage`** | 1-on-1 private messaging records with read receipts. | `sender`, `recipient`, `content`, `is_read`, `created_at`. |
| **`AuditEvent`** | Tamper-evident operational event log. | `event_type`, `actor_enrollment`, `description`, `target_id`, `timestamp`. |
| **`PlatformFeedback`** | Bug reports, proposals, and user feedback submissions. | `user`, `feedback_type`, `title`, `description`, `system_info`, `status`. |
| **`Contributor`** | Recognized open-source contributors and maintainers. | `user`, `name`, `enrollment_number`, `role`, `github_url`, `nominated_by`, `is_active`. |

### 3.2 Transit & Ridesharing Domain (`coordinate` app)

| Model | Primary Purpose | Key Fields |
| :--- | :--- | :--- |
| **`RideRequest`** | Ridesharing offer or passenger request. | `creator`, `route` (`NIT_TO_AIRPORT`, `AIRPORT_TO_NIT`, etc.), `custom_route_name`, `departure_time`, `total_spots`, `status` (`OPEN`, `FULL`, `COMPLETED`, `CANCELLED`), `visibility` (`MIXED`, `GIRLS_ONLY`, `FRIENDS_ONLY`). |
| **`RideParticipant`** | Confirmed passengers joined on a ride. | `ride`, `user`, `joined_at`, `is_host`. |
| **`RideJoinRequest`** | Pending requests from students seeking to join a ride. | `ride`, `applicant`, `status` (`PENDING`, `ACCEPTED`, `DECLINED`), `seat_count`. |
| **`RideWaitlist`** | FIFO queue for full rides when a confirmed passenger cancels. | `ride`, `user`, `position`, `status`, `created_at`. |
| **`RideReview`** | Post-ride peer punctuality and behavioral reviews. | `ride`, `reviewer`, `reviewed_user`, `rating` (1-5), `punctuality` (`ON_TIME`, `LATE`, `NO_SHOW`), `complaint`. |
| **`RideIncidentReport`** | Formal disciplinary escalations forwarded to Proctorial Board. | `ride`, `reporter`, `reported_user`, `incident_type`, `description`, `status`. |

---

## 4. Channels WebSockets Routing Architecture

### 4.1 Routing Configuration (`coordinate.routing` & `accounts.routing`)
WebSocket traffic is handled through asynchronous consumers:
```python
# Protocol Router (campus/asgi.py)
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter([
                path("ws/rides/<int:ride_id>/", RideChatConsumer.as_asgi()),
                path("ws/chat/<str:enrollment>/", DirectChatConsumer.as_asgi()),
            ])
        )
    ),
})
```

### 4.2 Security Guards on WebSocket Connections
1. **Authentication Check:** Unauthenticated socket handshakes are immediately rejected with close code `4401`.
2. **Access Control:**
   - In **Ride Chat**: Sockets confirm the user is a confirmed `RideParticipant` before accepting connection.
   - In **Direct Chat**: Sockets confirm a bidirectional `Friendship` exists between `request.user` and the target user. Strangers cannot open socket channels.
3. **Payload Sanitization:** Inbound messages are stripped of HTML tags and truncated to 2,000 characters before broadcasting to the channel group.


---

## 5. Early Launch Mode & Temporary Database Isolation Architecture

### 5.1 Motivation & Context
During end-of-term academic periods, student transit volume surges dramatically as thousands book cabs to Srinagar Airport and railway stations. Physical in-person identity verification at the Proctorial Board desk cannot scale quickly enough to meet this immediate demand. However, self-declared accounts are fundamentally **untrustworthy**. To prevent polluting the permanent institutional database or conflicting with real student records, Early Launch Mode segregates all early access activity into an isolated, temporary database (`temp_early_access.sqlite3`).

### 5.2 Control Surface & CLI Invocation
Early Launch Mode is toggled via command-line flag or environment configuration:
```bash
# Option 1: CLI invocation (extends Daphne runserver with auto-migration)
python manage.py runserver --early-launch 0.0.0.0:8000

# Option 2: Environment variable
EARLY_LAUNCH_MODE=True python manage.py runserver 0.0.0.0:8000

# Purge temporary database post-launch
python manage.py purge_early_launch [--force]
```

### 5.3 System Mechanics & Database Isolation
1. **Dynamic Database Routing:** When `EARLY_LAUNCH_MODE` is active:
   - `DATABASES['default']` points to `temp_early_access.sqlite3`.
   - `DATABASES['permanent']` retains a read connection to the real permanent database (`db.sqlite3` or PostgreSQL).
   - All early access user accounts, rides, messages, and sessions are written strictly to `temp_early_access.sqlite3`.
   - The permanent database is never modified or polluted.
2. **Untrusted Account Classification (`verified=False`):**
   - Self-declared users are marked `verified=False` to indicate untrusted status.
   - Profile badges, dashboard cards, and search listings display an explicit `Untrusted • Early Access` warning.
   - `coordinate.policies.is_verified_student` grants temporary transit privileges solely while `EARLY_LAUNCH_MODE=True`, without certifying the identity as trustworthy.
3. **Command Precedence & Auto-Migration:** `'accounts'` precedes `'daphne'` in `INSTALLED_APPS`, allowing `accounts.management.commands.runserver.Command` to auto-migrate `temp_early_access.sqlite3` and sync superuser credentials on startup.
4. **StatReloader Environment Propagation:** The `--early-launch` handler sets `os.environ['CAMPUS_EARLY_LAUNCH_MODE'] = 'True'`, ensuring worker processes inherit the temporary database across reloads.
5. **Zero Collision with Real Accounts:** Because databases are completely isolated, a student self-declaring with enrollment `2024BCSE001` in the temporary database can never overwrite, lock out, or collide with `2024BCSE001` in the permanent database.
6. **Clean Purge (`purge_early_launch`):** When the transit rush concludes, administrators execute `python manage.py purge_early_launch --force` to delete the temporary database. Standard mode resumes with the pristine permanent database.

---

## 6. Dynamic Ride Capacity Modification & Ejection Engine

### 6.1 Host Capacity Alterations
Ride hosts can alter the total capacity of an active ride post-creation (`1 <= total_spots <= 6`):
- **Capacity Expansion:** If the new capacity exceeds confirmed participants, ride status dynamically reverts from `FULL` to `OPEN`.
- **Capacity Reduction with Surplus Ejection:**
  - If the new capacity is less than the current count of confirmed passengers, the host cannot silently shrink the ride.
  - The host must explicitly pass `kick_passenger_ids` matching the exact number of surplus passengers to be removed.
  - Hosts cannot kick themselves.
  - Ejected passengers are notified, `RideParticipant` records are removed, and status recalculation occurs within an atomic database transaction.

---

## 7. Dynamic Favicon & Performance Optimization Architecture

### 7.1 Real-Time Canvas Favicon Engine
To visually reflect user personalization in browser tabs:
1. `templates/base.html` and `static/js/watermark.js` generate a 32x32 rounded-corner icon via HTML5 Canvas on the fly.
2. The dynamic icon uses OLED-black gradients, dark green background meshes, and borders/inner glyphs colored with the active theme accent (Emerald, Cyan, Indigo, Amber, Rose, etc.).
3. When custom hex accents are chosen, the canvas recalculates dynamically and updates `<link rel="icon">` via data URLs.
4. A static PNG fallback is served directly from `/favicon.ico` via a dedicated lightweight view in `campus.urls`.

### 7.2 High-Throughput Performance Optimizations
- **Instant Transitions:** Disabled the 880ms artificial Zen page transition delay by default (`nexus_zen_transitions: 'false'`), achieving instantaneous page changes while keeping transitions opt-in.
- **Font Rendering:** Removed blocking `@import` web fonts from `static/css/main.css` in favor of high-performance system typography and preloaded assets.
- **60fps Gear Animation:** Cached DOM element queries in `static/js/watermark.js` to eliminate DOM query thrashing during `requestAnimationFrame`.
- **Traffic Telemetry:** Kept `TrafficTelemetryMiddleware` synchronous with non-blocking cache lock acquisition (`_LOCK.acquire(blocking=False)`), preventing ASGI awaitable wrapper exceptions.
