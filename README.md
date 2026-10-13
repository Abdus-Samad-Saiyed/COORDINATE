# Campus Nexus

### One campus. Connected services.

Campus Nexus is a proposed modular platform designed to bring useful campus services together under a unified digital experience. It aims to provide a common entry point for student utilities, supported by shared identity management, service discovery, administration, and a maintainable backend architecture.

The first planned integration is **COORDINATE**, an existing student ride-sharing application. Future services may include campus announcements, events, lost-and-found, student marketplaces, and study-group coordination.

> **Status:** Planning and architecture stage. The architecture and features described below represent the intended direction of the project, not necessarily implemented functionality.

---

## Objectives

- **Unified access:** Provide a central directory for discovering campus services.
- **Shared identity:** Establish consistent authentication and authorization policies.
- **Modularity:** Organise services around clear functional boundaries.
- **Cross-platform support:** Provide responsive web and mobile experiences.
- **Administration:** Support account management, moderation, and operational monitoring.
- **Maintainability:** Prioritise clear architecture, automated testing, and reliable deployment.
- **Scalability:** Support growth through measured optimisation rather than premature infrastructure complexity.

## Repository Strategy

Campus Nexus and COORDINATE are separate projects with distinct responsibilities.

| Repository | Responsibility |
|---|---|
| `COORDINATE` | Existing student ride-sharing application and its development history |
| `Campus Nexus` | Umbrella platform, shared experience, service catalogue, and future integrations |

COORDINATE will retain its existing repository identity. Campus Nexus is a separate project, not a renaming or rebranding of the ride-sharing application.

The initial integration approach is to expose COORDINATE through the Campus Nexus service catalogue. Deeper integration may be considered later through documented APIs or another deliberately designed integration boundary.

The existing application should not be copied or rewritten wholesale without a clear technical justification.

---

## Architecture

Campus Nexus will initially follow a **modular monolith** architecture. Functional domains will have clear internal boundaries while sharing a straightforward application and deployment model.

Independent services may be considered later if measured requirements justify the additional operational complexity.

### High-Level Architecture

```mermaid
flowchart TB
    subgraph Clients
        WEB[React Web Client]
        MOBILE[React Native Mobile App]
    end

    API[Versioned REST API]
    APP[Django Application]

    subgraph Domains
        AUTH[Identity and Accounts]
        CATALOGUE[Service Catalogue]
        COORD[COORDINATE Integration]
        ADMIN[Administration and Analytics]
        NOTIFY[Notifications and Moderation]
    end

    DB[(PostgreSQL)]
    REDIS[(Redis)]
    WORKERS[Background Workers]

    WEB --> API
    MOBILE --> API
    API --> APP

    APP --> AUTH
    APP --> CATALOGUE
    APP --> COORD
    APP --> ADMIN
    APP --> NOTIFY

    APP --> DB
    APP -.-> REDIS
    APP -.-> WORKERS
