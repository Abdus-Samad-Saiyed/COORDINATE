# Campus Nexus — REST API (v1) & WebSockets Protocol Specification

---

## 1. REST API (v1) Specification

All versioned API endpoints reside under `/api/v1/`. Responses return UTF-8 encoded JSON payloads with standard HTTP status codes.

### 1.1 Service Catalogue Endpoints

#### `GET /api/v1/catalogue/`
List all umbrella services registered on Campus Nexus.
- **Access:** Public
- **Response:**
  ```json
  {
    "count": 4,
    "services": [
      {
        "id": "coordinate",
        "slug": "coordinate",
        "name": "COORDINATE",
        "tagline": "Campus Ride Sharing & Commute",
        "is_active": true,
        "features": ["Real-time discovery", "WebSockets live chat"]
      },
      {
        "id": "stationery_print",
        "slug": "print-hub",
        "name": "PRINT HUB",
        "is_active": false
      }
    ]
  }
  ```

#### `GET /api/v1/catalogue/<slug>/`
Retrieve metadata and operational status for an individual service offering.

---

### 1.2 Transit & Rides Endpoints (`coordinate`)

#### `GET /api/v1/rides/`
Search and filter open ride listings.
- **Access:** Authenticated students
- **Query Parameters:**
  - `route`: Filter by route code (e.g. `NIT_TO_AIRPORT`).
  - `visibility`: `MIXED`, `GIRLS_ONLY`, `FRIENDS_ONLY`.
  - `ordering`: `time_asc` (default) or `time_desc`.
- **Response (200 OK):**
  ```json
  [
    {
      "id": 14,
      "route": "NIT_TO_AIRPORT",
      "route_display": "NIT Srinagar -> Srinagar Airport",
      "departure_time": "2026-10-18T14:30:00+05:30",
      "total_spots": 4,
      "spots_remaining": 2,
      "visibility": "MIXED",
      "status": "OPEN",
      "creator": {
        "enrollment_number": "2024BCSE065",
        "name": "Abdus Samad Saiyed",
        "punctuality_rate": 96.5
      }
    }
  ]
  ```

#### `POST /api/v1/rides/`
Publish a new ride-share journey.
- **Request Body:**
  ```json
  {
    "route": "NIT_TO_AIRPORT",
    "departure_time": "2026-10-18 14:30",
    "total_spots": 4,
    "visibility": "MIXED",
    "notes": "Flight departure at 17:45. Leaving Main Gate sharp."
  }
  ```

#### `GET /api/v1/rides/<ride_id>/`
Retrieve full ride details, confirmed participants, and co-passenger notes.
- **Access Guard:** Host or confirmed participants only. Non-participants receive HTTP 404.

---

## 2. WebSockets Real-Time Protocol Specification

### 2.1 Direct Friend Chat (`ws/chat/<enrollment>/`)
Provides sub-second end-to-end message relay between confirmed friends.

#### Connection Handshake
- **URL:** `wss://nexus.nitsri.ac.in/ws/chat/2024BCSE065/`
- **Verification:** Automatically checks active session and verifies `Friendship` table. Unrelated strangers receive close code `4403`.

#### Client-to-Server Inbound Packet
```json
{
  "action": "send_message",
  "content": "Hey! Are you heading to the library before noon?"
}
```

#### Server-to-Client Broadcast Packet
```json
{
  "type": "chat_message",
  "message_id": 4182,
  "sender": "2024BCSE065",
  "sender_name": "Abdus Samad Saiyed",
  "content": "Hey! Are you heading to the library before noon?",
  "timestamp": "2026-10-14T01:23:45+00:00"
}
```

---

### 2.2 Ride Group Coordination Room (`ws/rides/<ride_id>/`)
Provides real-time group communication for all passengers joined on a ride.

#### Connection Handshake
- **URL:** `wss://nexus.nitsri.ac.in/ws/rides/14/`
- **Verification:** Sockets verify `RideParticipant.objects.filter(ride_id=14, user=request.user).exists()`. Non-joined users are immediately disconnected.

#### Inbound & Broadcast Message Packets
```json
{
  "type": "ride_chat_message",
  "sender": "2024BCSE065",
  "sender_name": "Abdus Samad Saiyed",
  "content": "Cab driver has arrived at the Main Security Gate. White Innova JK01AB1234.",
  "timestamp": "2026-10-18T14:15:00+05:30"
}
```
