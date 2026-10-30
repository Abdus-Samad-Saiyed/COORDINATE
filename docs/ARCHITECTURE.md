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
