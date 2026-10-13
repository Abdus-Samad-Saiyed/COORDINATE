# Campus Nexus and COORDINATE
## Internal Stabilisation and Platform Roadmap

**Last updated:** 13 October 2026  
**Purpose:** Engineering planning document. This document contains implementation guidance and acceptance gates for maintainers; it is not intended to be copied into a public repository description.

---

## 1. Project boundaries

- **COORDINATE** is the existing student ride-sharing project. Preserve its repository identity and development history.
- **Campus Nexus** is a separate, new umbrella-platform project for the service directory, shared platform experience, and future campus services.
- Do not describe planned Campus Nexus capabilities as already implemented.
- Begin with a service-directory link to COORDINATE. Consider deeper API or code integration only after the relevant stabilization gates pass.
- Do not start by copying or rewriting the entire COORDINATE codebase.

## 2. Target architecture

Start with a modular monolith and explicit domain boundaries. Avoid splitting modules into microservices until measured scaling, isolation, or deployment needs justify the operational cost.

```text
Web client (React + TypeScript)       Mobile client (React Native)
                 \                         /
                  \                       /
                    Versioned API (/api/v1)
                              |
                 Django + Django REST Framework
                              |
        +---------------------+---------------------+
        |           |           |                  |
     Identity   Catalogue   COORDINATE       Admin/Analytics
        |                     boundary
        +---------------------+---------------------+
                              |
             +----------------+----------------+
             |                |                |
         PostgreSQL         Redis       Background workers
         durable data   cache/Channels  when justified
                              |
                       ASGI / WebSockets
```

Production deployment should eventually include TLS termination, health checks, structured logs, metrics, backups, recovery procedures, and shared persistent storage. Multiple application instances should be introduced only with a deployment design that supports shared state correctly.

## 3. Public documentation boundary

Public-facing README files and repository descriptions should cover purpose, current status, architecture, verified capabilities, limitations, setup instructions when available, roadmap at a suitable level, and license.

Keep maintainer-only implementation instructions, private planning rationale, résumé or profile considerations, secret-handling reminders specific to an individual, and task-by-task remediation notes out of public repository descriptions. Detailed engineering tasks belong in this roadmap or the issue tracker.

## 4. License

All projects in this plan are intended to use the **MIT License**. Include a `LICENSE` file in each repository and ensure the copyright holder/year fields are accurate for that repository. Do not claim a license is applied until the file is actually committed.

## 5. Gated implementation roadmap

Advance only when the acceptance criteria for the current level are met. Record test evidence rather than relying on the presence of code alone.

### Level 0: Baseline and containment

**Work**
- Establish a reproducible local environment and record current runtime behavior.
- Inventory routes, models, settings, templates, WebSocket consumers, scheduled tasks, and deployment configuration.
- Identify exposed secrets, unsafe debug settings, untrusted uploads, and accidental data disclosure.
- Add or verify repository ignore rules and ensure build artifacts and local databases are not accidentally committed.

**Gate**
- A maintainer can reproduce the app from documented steps.
- Known critical risks are tracked, and no active secret is knowingly committed.
- A baseline test run and issue inventory are recorded.

### Level 1: Authentication, authorization, and privacy

**Work**
- Audit password creation, reset, change, and administrative account operations for framework-standard password hashing and validation.
- Add throttling to login, application submission, password recovery, and other abuse-prone endpoints.
- Make login identity normalization consistent, including case handling where applicable.
- Review authorization at every server-side boundary; hiding a button is not access control.
- Ensure complaints, profiles, phone numbers, applications, and other private data are only visible to authorized users.
- Avoid logging passwords, raw session identifiers, tokens, or private complaint contents.

**Gate**
- Automated tests cover unauthorized access, data leakage, throttling, and account recovery.
- Sensitive endpoints enforce server-side permissions.
- Security-sensitive settings fail safely in production.

### Level 2: Ride lifecycle and data integrity

**Work**
- Define allowed ride states and transitions, including full, cancelled, departed, and completed states.
- Reject invalid or past departure times according to an explicit policy.
- Ensure expired or completed rides do not leave participants locked out of unrelated functionality.
- Prevent kicked or removed participants from rejoining unless the policy explicitly permits it.
- Preserve appropriate history rather than hard-deleting records needed for audit or dispute resolution.
- Make seat allocation and participant changes safe under concurrent requests, using database constraints and transactions.
- Correct timezone handling and use consistent server-side date/time rules.
- Verify creator eligibility against any ride visibility restrictions.
- Make reliability and review counters derive from validated events or authoritative aggregates rather than unsynchronized ad hoc increments.

**Gate**
- Tests cover boundary times, timezone transitions, full rides, cancellations, removals, concurrent joins, duplicate actions, and history retention.
- Database constraints and transaction behavior are verified against PostgreSQL.

### Level 3: Messaging, friendships, and community workflows

**Work**
- Review friend-request visibility, acceptance/rejection, blocking, and friends-only visibility.
- Ensure WebSocket group identifiers are normalized consistently and membership is authorized on connect and on every relevant action.
- Handle text and binary frames deliberately; reject unsupported payloads safely.
- Return clear feedback for failed sends rather than silently dropping messages.
- Add message rate limits and connection controls.
- Resolve duplicate review/rating races and validate allowed rating values.
- Ensure HTTP/HTMX responses match the client expectations and remove obsolete or unreachable fragments.

**Gate**
- Tests cover unauthorized room access, reconnect behavior, rate limits, duplicate reviews, malformed messages, and UI response contracts.

### Level 4: Campus Nexus web foundation

**Work**
- Create the new Campus Nexus repository independently of COORDINATE.
- Build the central landing page and configurable service catalogue.
- Establish a shared design system and responsive navigation.
- Implement the proposed gear-and-clock watermark as a decorative element synchronized to browser system time.
- Respect reduced-motion settings and ensure the watermark cannot intercept clicks or obscure readable content.
- Link to COORDINATE as the first listed service without implying that it has already been merged.

**Gate**
- The landing page is responsive, keyboard-usable, accessible enough for the project's baseline, and clear about which services are live versus planned.
- The COORDINATE link works, and unavailable services are not represented as live.

### Level 5: Versioned API and mobile client

**Work**
- Define API contracts and a versioning policy before exposing client-specific endpoints.
- Build React/TypeScript web integration and a React Native client against the same server-side permission rules.
- Use a shared authentication/session design suitable for web and mobile without exposing credentials in logs or URLs.
- Define loading, error, offline, and expired-session behavior.
- Add contract tests for critical API routes.

**Gate**
- Web and mobile clients use the same authoritative business rules.
- API permissions and input validation are tested independently of the UI.

### Level 6: Administration, sessions, and analytics

**Work**
- Add role-controlled account/application management and moderation workflows.
- Track sessions and security-relevant events with data minimization and retention limits.
- Build operational dashboards for active sessions, authentication failures, ride states, complaint workflow status, error rates, WebSocket failures, and background-job failures where applicable.
- Provide exportable reports with permission checks, audit events, field minimization, and safe handling of generated files.
- Separate sessions from unique users and separate complaint counts from any conclusion about the validity of complaints.

**Gate**
- Dashboard numbers have documented definitions and are tested against source records.
- Exports cannot bypass authorization and do not expose unnecessary personal information.
- Administrative actions and sensitive exports are auditable.

### Level 7: Shared infrastructure and measured scaling

**Work**
- Use PostgreSQL for production relational data.
- Introduce Redis for shared Channels state/cache where required; do not rely on process-local memory for cross-instance coordination.
- Make app instances stateless where practical and externalize durable uploads.
- Add background workers only for work that benefits from asynchronous execution.
- Measure slow queries, connection use, latency, and resource saturation before optimizing.
- Validate shared session, cache, WebSocket, and job behavior across multiple instances.

**Gate**
- A documented load test demonstrates the current bottleneck and verifies the chosen improvement.
- Multiple instances do not cause split session state, lost messages, or inconsistent job execution.

### Level 8: Production deployment and delivery

**Work**
- Separate development, test, and production settings.
- Require secure secret injection, HTTPS, correct proxy/host/CSRF configuration, secure cookies, and restrictive production defaults.
- Review static asset delivery and third-party integrity where external assets are used.
- Add CI checks for formatting, tests, migrations, dependency/security checks, and build artifacts.
- Establish database backup, restore drills, migration procedures, and rollback plans.
- Verify container ignore rules and ensure images do not include secrets, local databases, or unnecessary development files.

**Gate**
- A clean deployment can be built from documented steps.
- Backup restoration and rollback are tested, not merely documented.
- Production settings and health checks are verified in the target environment.

### Level 9: Pilot and rollout

**Work**
- Run a limited pilot with clear feedback and incident-reporting paths.
- Monitor performance, error rates, support volume, and privacy/security reports.
- Fix critical issues before broadening access.
- Publish user-facing explanations of what data is collected and how moderation and retention work.

**Gate**
- No unresolved critical security or privacy issue remains.
- Core workflows have passed acceptance tests.
- Monitoring, backup, incident response, and ownership responsibilities are clear.

## 6. Known audit areas for COORDINATE

The following are investigation and test areas from the prior audit, not blanket claims about the current state of the code. Confirm each against the current repository before treating it as an active defect.

- Ride-history route reachability and access control.
- Gender/visibility validation for ride creators and participants.
- Complaint privacy and application queue validation/rejection.
- Password reset/change flows and administrative password handling.
- Login/application throttling and case-normalized identity lookup.
- Past or expired ride behavior and invalid departure-time acceptance.
- Phone-number visibility and unnecessary collection.
- Removed participants rejoining and preservation of useful history.
- Reliability counters, concurrent participant updates, and duplicate review submission.
- UTC/local-time inconsistencies.
- WebSocket binary frames, dropped sends, group-name normalization, membership checks, and rate limits.
- Departure-time buffers and boundary conditions.
- Friend-request visibility and invalid query parameters.
- ASGI/Channels production configuration.
- Secret exposure in dumps, settings, container builds, or repository files.
- TLS proxy, CSRF, host, cookie, and debug settings.
- Static asset integrity, migrations, and PostgreSQL compatibility.

## 7. Operating principles

1. **Security before feature count.** Do not add a new module on top of an unsafe identity or authorization layer.
2. **Evidence before status claims.** A feature is complete only when implementation and relevant tests support that claim.
3. **Privacy by default.** Collect the minimum necessary data, restrict access, define retention, and audit exports.
4. **Measure before scaling.** Prefer a simple architecture until real workload data justifies more complexity.
5. **Preserve project boundaries.** Campus Nexus and COORDINATE are related but distinct repositories.
6. **Make gates explicit.** Do not advance merely because a checklist has been written; record test results and unresolved risks.
