# The Campus Nexus Manifesto & Governance Charter

**Platform Version:** 2.4.0  
**Founding Author & Architect:** Abdus Samad Saiyed (`2024BCSE065`)  
**Institution:** National Institute of Technology Srinagar (NIT Srinagar)  
**Motto:** *Sic Itur Ad Astra* ("Thus one journeys to the stars")  

---

## 1. The Core Manifesto

Campus Nexus was conceived and engineered under a single foundational conviction:

> **A university campus is not an anonymous open marketplace; it is a shared physical community of scholars, commuters, and peers. Digital infrastructure built for this community must reinforce real-world trust, mutual accountability, and sovereign student utility.**

Modern software platforms often treat users as anonymized data points, encouraging detached, unaccountable interactions. Campus Nexus rejects this paradigm. We are building a public digital utility designed to solve tangible daily friction on campus—starting with commuter ride coordination through **COORDINATE**, and extending to student governance, academic exchanges, and campus life.

This utility belongs to the student body of NIT Srinagar. It does not exist to harvest private data, monetize attention, or enable anonymous abuse. It exists to serve as the trustworthy nervous system of campus coordination.

---

## 2. Design & Development Philosophy

### I. The Physical Root of Trust
Digital credentials alone (usernames, passwords, arbitrary emails) can be forged, shared, or abandoned. A platform facilitating shared physical vehicles in the real world cannot rely on unanchored digital self-assertion.

* **Dual-Layer Verification:** An account begins digitally (verifying inbox control via single-use email OTP), but **it is born into the verified student collective only when anchored to physical reality**.
* **The In-Person Verification Desk:** Every verified account must be validated in person by an authorized student administrator or contributor who physically checks the student's official Institute ID Card. This single operational invariant eliminates botnets, duplicate sockpuppets, unauthorized external infiltrators, and malicious bad actors from the student network.

### II. Physical Accountability vs. Public Privacy
Our privacy model distinguishes between **external internet voyeurism** and **in-person vehicle coordination**:

1. **Total Isolation from the External Web:** Outside entities, web crawlers, search engines, and unverified visitors see only public institutional landing pages (`/`, `/about/`, `/contact/`, `/contributors/`, `/services/`). They have zero access to student registers, profiles, trip logs, or directories.
2. **Mutual Transparency in Shared Physical Spaces:** When students enter a shared vehicle traveling across Jammu & Kashmir highways, **anonymity is strictly prohibited**. There is no "anonymous mode" inside a moving vehicle. Co-passengers and ride hosts mutually share verified student names, enrollment numbers, and phone numbers. Knowing who you are traveling with is an uncompromisable safety requirement.
3. **Contextual Disclosure for Browsing Peers:** A verified student browsing open rides sees the ride route, host identity, and aggregate occupancy, but **cannot view passenger rosters or passenger phone numbers** until they become a confirmed participant in that ride.

### III. Anti-Farming & Public Fair Play
Campus Nexus is an essential campus utility, not a gamified social app. When reputation metrics (such as on-time percentages and reliability badges) are introduced, people naturally attempt to farm them.

* **Every Ride Counts for Commute History:** Every verified group trip completed increments `rides_completed` permanently.
* **Capped Reliability Bonuses:** To prevent mutual collusion or artificial score farming, reliability score bonuses (`on_time_count`) are rate-limited to a maximum of **3 boosts per 15-day rolling window**. A student who rides legitimately builds an honest, verifiable track record over time; a user attempting to cycle rapid micro-rides cannot inflate their standing.

### IV. Transparent Product Communication
If a capability is not yet operational, we communicate the truth clearly and respectfully:
* Direct SMS integration requires telecom DLT registration and allocated recurring capital. Until those resources are procured, the UI controls remain visible but darkened with an **"Upcoming Release"** badge and explanatory roadmap guidance, while verification codes are reliably delivered via our configured Google SMTP relay (`noreply.campus.nexus@gmail.com`). We promise features only when we intend to deliver them.

### V. Code Integrity & Operational Simplicity
* **Zero Hidden Magic:** Clean, idiomatic Python and Django without excessive third-party middleware bloat.
* **Deterministic Verification:** Fast, isolated unit tests executing against in-memory architectures in seconds.
* **Immutable Audit Evidence:** Destructive actions never erase security evidence. When a ride empties, it is soft-cancelled (`status = 'CANCELLED'`), preserving safety reports and chat records. When a user closes an account, it is soft-deleted (`is_deleted = True`), preserving historical ride logs and past review integrity.

---

## 3. Data Governance & Access Control Matrix

### Who Owns What?

| Domain | Owner | Rights & Retention Principles |
| :--- | :--- | :--- |
| **Personal Profile & Contact Settings** | The Student | Can toggle profile photo visibility, search discovery, and contact visibility to friends. Can request account closure at any time. |
| **Direct Peer Messages** | Sender & Receiver | Private between mutually confirmed friends. Never exposed to directory search or other students. |
| **Active Ride Chat** | Confirmed Participants | Accessible only to confirmed riders of that specific trip during the coordination window (departure + 2 hours). |
| **Ride Roster & Logistics** | Confirmed In-Ride Cohort | Shared mutually between confirmed riders to coordinate in-person pickup. |
| **Safety Incident Reports & Audit Events** | The Platform / Institute | Permanently retained and immutable. Preserved even if an involved account is soft-deleted to ensure disciplinary and safety accountability. |
| **Institutional Account Applications** | Administrative Desk | Maintained under administrative confidentiality for physical verification and record auditing. |

---

### Access Control Matrix

```
Legend:
[●] Full Access / View / Modify
[○] Read-Only Access
[Mutual] Visible only between mutually confirmed peers in that specific interaction
[Consent] Visible only when explicit affirmative consent is granted
[✕] No Access / Hidden / Forbidden
```

| Resource / Endpoint | Public (Anon) | Unverified Applicant | Verified Student | Confirmed Ride Co-Passenger | Staff Operator | Root Superuser |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Public Landing & Info (`/`, `/about/`)** | ○ | ○ | ○ | ○ | ○ | ○ |
| **Service Catalogue (`/services/`)** | ○ | ○ | ○ | ○ | ○ | ○ |
| **Account Application (`/apply/`)** | ● | ● | ✕ | ✕ | ✕ | ✕ |
| **Student Directory Search (`/search/`)** | ✕ | ✕ | ○ | ○ | ○ | ● |
| **Peer Profile (Name, Branch, Degree)** | ✕ | ✕ | ○ | ○ | ○ | ● |
| **Peer Phone & Email on Profile** | ✕ | ✕ | [Consent] | [Consent] | ○ | ● |
| **Ride Discovery Board (`/coordinate/`)** | ✕ | ✕ | ○ | ○ | ○ | ● |
| **Browse Open Ride Roster (Names/Phones)** | ✕ | ✕ | ✕ | [Mutual] | ○ | ● |
| **Confirmed Ride Chat (`/ws/ride/`)** | ✕ | ✕ | ✕ | ● | ✕ | ✕ |
| **Host Ride Controls (Accept / Kick)** | ✕ | ✕ | ✕ | Host Only | ✕ | ● |
| **Operations Console (`/operations/`)** | ✕ | ✕ | ✕ | ✕ | ● | ● |
| **Approve / Reject ID Applications** | ✕ | ✕ | ✕ | ✕ | ● | ● |
| **Physical Password Reset Resolution** | ✕ | ✕ | ✕ | ✕ | ● | ● |
| **CSV Platform Data Exports** | ✕ | ✕ | ✕ | ✕ | [Step-Up] | [Step-Up] |
| **Superuser Governance (`/operations/superusers/`)** | ✕ | ✕ | ✕ | ✕ | ✕ | [Step-Up] |

---

## 4. What Information Must Be Shared (And What Must Never Be)

### Mandatory Shared Information
1. **In-Vehicle Coordination:**
   * **Verified Name & Enrollment Number:** Passengers and hosts must be able to verify each other's identity before boarding a private or shared vehicle.
   * **Active Phone / WhatsApp Number:** Co-passengers must be reachable to coordinate physical pickup points (e.g. NIT Gate, Lal Chowk, Hazratbal).
2. **Directory & Peer Interaction:**
   * **Degree, Branch, and Joining Year:** Visible to verified students to allow branch-level academic and commuter collaboration.
   * **Commuter Reliability Percentage:** Cumulative on-time percentage displayed to encourage punctual arrivals and respectful travel.

### Strictly Guarded / Private Information
1. **Authentication Secrets:** Password hashes, raw OTP verification codes, and WebAuthn cryptographic credentials are never exposed, logged, or returned in API responses.
2. **Unconsented Direct Contact:** A student's phone number and email are hidden on their profile page by default from non-friends.
3. **Application Identification:** An applicant's application tracking number and submitted government/institute document details are restricted solely to operational review staff.
4. **Spectator Ride Rosters:** Browsing spectators on the ride discovery board can never scrape the passenger list or contact info of open rides they have not joined.

---

## 5. Administrative Stewardship & Governance Principles

Those who hold administrative privileges on Campus Nexus are **servants of the student community, not owners of it**. Every administrative power is bounded by cryptographic and architectural safeguards:

1. **Anti-Lockout Invariant:** The system strictly prevents revoking or deleting the sole remaining active superuser under all circumstances. Administrative abandonment is impossible.
2. **No Backdoor Privilege Escalations:** Superuser privileges cannot be granted through Django Admin checkboxes or bulk action shortcuts. They can only be managed through the dedicated, audited `/operations/superusers/` console under fresh step-up authentication.
3. **Mandatory Multi-Factor Authentication:** Any account holding staff or superuser privileges is required to complete Two-Factor Authentication on every login session.
4. **Freshness Verification on Sensitive Actions:** Destructive administrative operations (soft-deleting accounts, granting superuser status, exporting data) require proof of recent authentication (< 15 minutes) or explicit password confirmation.
5. **Formula Injection Sanitization:** Every CSV export generated by operators sanitizes spreadsheet formulas (`=`, `+`, `-`, `@`) to protect administrative workstations from client-side spreadsheet execution attacks.

---

## 6. A Message to Future Maintainers

If you are a student developer, contributor, or future lead maintaining Campus Nexus after us, remember why this software was built:

* **Keep it independent:** Do not surrender this platform to corporate ad networks, third-party trackers, or predatory monetization schemes.
* **Preserve the physical root of trust:** The moment you abandon in-person verification for lazy automated signups, you surrender the platform to spam, bots, and bad actors.
* **Protect the commuter:** Every line of code written for COORDINATE affects real students traveling in real weather across real terrain. Treat every bug fix as an issue of campus safety.
* **Build with craftsmanship:** Keep the code readable, the architecture modular, the tests green, and the documentation intact.

*Sic Itur Ad Astra.*

---
*Authored on October 30, 2026, on the campus of NIT Srinagar.*
